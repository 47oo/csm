/**
 * Parallel batch scheduler for the subagent extension.
 *
 * Owns the queued/running/completed/failed/aborted lifecycle and the
 * concurrency limit. The actual work is injected through a `TaskExecutor`, so
 * the scheduler can be tested offline with a fake executor and fake child
 * processes.
 *
 * Guarantees:
 *   - Status is explicit; no `exitCode === 0` sentinel is used to mean "running".
 *   - On cancellation, queued tasks are aborted without starting, running tasks
 *     are terminated, and the batch resolves only after every started task has
 *     settled (its process actually closed).
 *   - An exception from one task is captured and the batch still waits for the
 *     others; completed results are preserved.
 */

import type { PlannedTask, TaskStatus } from "./task-plan.ts";

export interface TaskRunOutcome<TResult> {
	status: "completed" | "failed" | "aborted";
	result: TResult;
}

export interface RunningTask<TResult> {
	/** Resolves once the underlying process has been fully reaped. */
	readonly settled: Promise<TaskRunOutcome<TResult>>;
	/** Request termination. Must be idempotent. */
	terminate(): void;
}

export interface TaskExecutor<TResult> {
	/**
	 * Start one task synchronously and return a handle. `report` publishes a
	 * partial result for streaming; it must not be used to mark completion.
	 */
	start(spec: PlannedTask, report: (partial: TResult) => void): RunningTask<TResult>;
	/** Build the result for a task aborted before it was ever started. */
	abortedResult(spec: PlannedTask, reason: string): TResult;
}

export interface TaskSlot<TResult> {
	id: string;
	index: number;
	agent: string;
	task: string;
	status: TaskStatus;
	/** Latest partial (while running) or final result. Undefined before start. */
	result: TResult | undefined;
	startedAt?: number;
	endedAt?: number;
	/** Set when the task was aborted before starting. */
	abortReason?: string;
}

export interface BatchOptions<TResult> {
	tasks: PlannedTask[];
	concurrency: number;
	executor: TaskExecutor<TResult>;
	signal?: AbortSignal;
	onUpdate?: (slots: ReadonlyArray<TaskSlot<TResult>>) => void;
	onSettled?: (slot: TaskSlot<TResult>) => void;
}

export interface BatchOutcome<TResult> {
	slots: TaskSlot<TResult>[];
	cancelled: boolean;
	errors: unknown[];
}

/**
 * Run `tasks` with at most `concurrency` in flight. Never rejects: per-task and
 * infrastructure errors are collected in `errors` after all work settles.
 */
export async function runTaskBatch<TResult>(options: BatchOptions<TResult>): Promise<BatchOutcome<TResult>> {
	const { tasks, executor, signal, onUpdate, onSettled } = options;
	const taskCount = tasks.length;
	const concurrency = Math.max(1, Math.min(options.concurrency, taskCount || 1));
	const errors: unknown[] = [];
	let cancelled = false;
	let nextIndex = 0;
	let abortListener: (() => void) | undefined;
	const running = new Map<number, RunningTask<TResult>>();

	const slots: TaskSlot<TResult>[] = tasks.map((task) => ({
		id: task.id,
		index: task.index,
		agent: task.agent,
		task: task.task,
		status: "queued",
		result: undefined,
	}));

	const notify = () => {
		if (!onUpdate) return;
		try {
			onUpdate(slots.map((slot) => ({ ...slot })));
		} catch (error) {
			errors.push(error);
		}
	};

	const notifySettled = (slot: TaskSlot<TResult>) => {
		if (!onSettled) return;
		try {
			onSettled(slot);
		} catch (error) {
			errors.push(error);
		}
	};

	const markAborted = (index: number, reason: string) => {
		const slot = slots[index];
		slot.status = "aborted";
		slot.abortReason = reason;
		slot.endedAt = Date.now();
		try {
			slot.result = executor.abortedResult(tasks[index], reason);
		} catch (error) {
			errors.push(error);
		}
		notifySettled(slot);
	};

	const requestCancel = () => {
		if (cancelled) return;
		cancelled = true;
		for (let i = 0; i < slots.length; i++) {
			if (slots[i].status === "queued") markAborted(i, "aborted before start");
		}
		for (const handle of running.values()) {
			try {
				handle.terminate();
			} catch (error) {
				errors.push(error);
			}
		}
		notify();
	};

	if (signal) {
		if (signal.aborted) {
			requestCancel();
		} else {
			abortListener = () => requestCancel();
			signal.addEventListener("abort", abortListener, { once: true });
		}
	}

	const runOne = async (index: number): Promise<void> => {
		// A cancellation may have aborted this slot after the worker took it.
		if (cancelled || slots[index].status !== "queued") return;
		const spec = tasks[index];
		const slot = slots[index];
		slot.status = "running";
		slot.startedAt = Date.now();
		notify();

		let handle: RunningTask<TResult>;
		try {
			handle = executor.start(spec, (partial) => {
				slot.result = partial;
				notify();
			});
		} catch (error) {
			errors.push(error);
			slot.status = "failed";
			slot.endedAt = Date.now();
			notifySettled(slot);
			notify();
			return;
		}

		running.set(index, handle);
		try {
			const outcome = await handle.settled;
			slot.status = outcome.status;
			slot.result = outcome.result;
		} catch (error) {
			errors.push(error);
			slot.status = "failed";
		} finally {
			running.delete(index);
		}

		slot.endedAt = Date.now();
		notifySettled(slot);
		notify();
	};

	const worker = async () => {
		while (!cancelled) {
			const index = nextIndex++;
			if (index >= taskCount) return;
			await runOne(index);
		}
	};

	try {
		await Promise.all(Array.from({ length: Math.max(1, concurrency) }, () => worker()));
	} finally {
		if (abortListener && signal) signal.removeEventListener("abort", abortListener);
	}

	return { slots, cancelled, errors };
}