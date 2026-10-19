/**
 * Offline tests for the parallel batch scheduler.
 *
 * Uses a fake executor and fake handles: no real child process and no model
 * call is involved. Run with:  node --test .pi/extensions/subagent/*.test.ts
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { runTaskBatch, type RunningTask, type TaskExecutor, type TaskRunOutcome } from "./batch.ts";
import type { PlannedTask } from "./task-plan.ts";

interface FakeResult {
	label: string;
	aborted?: boolean;
	reason?: string;
}

interface HandleState {
	terminated: boolean;
	resolve: (outcome: TaskRunOutcome<FakeResult>) => void;
	reject: (error: unknown) => void;
	report: (partial: FakeResult) => void;
}

class FakeExecutor implements TaskExecutor<FakeResult> {
	started: string[] = [];
	active = 0;
	maxActive = 0;
	readonly states = new Map<string, HandleState>();

	start(spec: PlannedTask, report: (partial: FakeResult) => void): RunningTask<FakeResult> {
		this.started.push(spec.id);
		this.active += 1;
		this.maxActive = Math.max(this.maxActive, this.active);

		let resolve!: (outcome: TaskRunOutcome<FakeResult>) => void;
		let reject!: (error: unknown) => void;
		const settled = new Promise<TaskRunOutcome<FakeResult>>((res, rej) => {
			resolve = res;
			reject = rej;
		});
		const state: HandleState = { terminated: false, resolve, reject, report };
		this.states.set(spec.id, state);

		return {
			settled: settled.finally(() => {
				this.active -= 1;
			}),
			terminate: () => {
				state.terminated = true;
			},
		};
	}

	abortedResult(spec: PlannedTask, reason: string): FakeResult {
		return { label: spec.id, aborted: true, reason };
	}

	settle(id: string, status: "completed" | "failed" | "aborted", label = id): void {
		const state = this.states.get(id);
		if (!state) throw new Error(`task ${id} was not started`);
		state.resolve({ status, result: { label } });
	}

	rejectWith(id: string, error: unknown): void {
		const state = this.states.get(id);
		if (!state) throw new Error(`task ${id} was not started`);
		state.reject(error);
	}
}

function planned(index: number, id?: string): PlannedTask {
	return {
		index,
		id: id ?? `task-${index + 1}`,
		idProvided: Boolean(id),
		declared: false,
		agent: "worker",
		task: `do ${index}`,
		cwd: "/tmp",
		rawWriteScope: [],
		writeScope: [],
		resources: [],
	};
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test("runs at most `concurrency` tasks at once and respects order", async () => {
	const executor = new FakeExecutor();
	const tasks = [0, 1, 2, 3, 4].map((i) => planned(i));
	const outcomePromise = runTaskBatch<FakeResult>({ tasks, concurrency: 2, executor });

	await flush();
	assert.equal(executor.maxActive, 2);
	assert.deepEqual(executor.started, ["task-1", "task-2"]);

	executor.settle("task-1", "completed");
	await flush();
	assert.deepEqual(executor.started, ["task-1", "task-2", "task-3"]);

	executor.settle("task-2", "completed");
	executor.settle("task-3", "completed");
	await flush();
	assert.equal(executor.maxActive, 2);
	assert.deepEqual(executor.started, ["task-1", "task-2", "task-3", "task-4", "task-5"]);

	executor.settle("task-4", "completed");
	executor.settle("task-5", "completed");
	const outcome = await outcomePromise;

	assert.deepEqual(
		outcome.slots.map((s) => s.status),
		["completed", "completed", "completed", "completed", "completed"],
	);
	assert.equal(outcome.cancelled, false);
	assert.deepEqual(outcome.errors, []);
});

test("tracks explicit queued/running/completed/failed lifecycle with streaming updates", async () => {
	const executor = new FakeExecutor();
	const tasks = [planned(0), planned(1)];
	const snapshots: string[][] = [];
	const settledStatuses: string[] = [];
	const outcomePromise = runTaskBatch<FakeResult>({
		tasks,
		concurrency: 2,
		executor,
		onUpdate: (slots) => snapshots.push(slots.map((s) => s.status)),
		onSettled: (slot) => settledStatuses.push(`${slot.id}:${slot.status}`),
	});

	await flush();
	// Both are running, neither has been declared complete via an exit-code sentinel.
	const lastSnapshot = snapshots[snapshots.length - 1];
	assert.deepEqual(lastSnapshot, ["running", "running"]);

	executor.states.get("task-1")?.report({ label: "partial" });
	const finalSnapshot = snapshots[snapshots.length - 1];
	assert.deepEqual(finalSnapshot, ["running", "running"], "a partial report must not settle the batch");

	executor.settle("task-1", "completed", "one");
	executor.settle("task-2", "failed", "two");
	const outcome = await outcomePromise;

	assert.deepEqual(
		outcome.slots.map((s) => [s.status, s.result?.label]),
		[
			["completed", "one"],
			["failed", "two"],
		],
	);
	assert.ok(settledStatuses.includes("task-1:completed"));
	assert.ok(settledStatuses.includes("task-2:failed"));
});

test("cancellation aborts queued tasks without starting them and terminates running ones", async () => {
	const executor = new FakeExecutor();
	const controller = new AbortController();
	const tasks = [0, 1, 2, 3].map((i) => planned(i));
	const outcomePromise = runTaskBatch<FakeResult>({
		tasks,
		concurrency: 2,
		executor,
		signal: controller.signal,
	});

	await flush();
	assert.deepEqual(executor.started, ["task-1", "task-2"]);

	controller.abort();
	await flush();
	assert.equal(executor.states.get("task-1")?.terminated, true);
	assert.equal(executor.states.get("task-2")?.terminated, true);

	// The batch must not resolve until every started task has settled.
	let resolved = false;
	outcomePromise.then(() => {
		resolved = true;
	});
	await flush();
	assert.equal(resolved, false);

	executor.settle("task-1", "aborted", "one");
	await flush();
	assert.equal(resolved, false, "must wait for the second started task too");
	executor.settle("task-2", "aborted", "two");

	const outcome = await outcomePromise;
	assert.equal(resolved, true);
	assert.deepEqual(executor.started, ["task-1", "task-2"], "queued tasks must not start after abort");
	assert.deepEqual(
		outcome.slots.map((s) => s.status),
		["aborted", "aborted", "aborted", "aborted"],
	);
	assert.equal(outcome.cancelled, true);
	assert.deepEqual(
		outcome.slots.slice(2).map((s) => s.abortReason),
		["aborted before start", "aborted before start"],
	);
});

test("an already-aborted signal starts no task", async () => {
	const executor = new FakeExecutor();
	const controller = new AbortController();
	controller.abort();
	const outcome = await runTaskBatch<FakeResult>({
		tasks: [planned(0), planned(1)],
		concurrency: 2,
		executor,
		signal: controller.signal,
	});

	assert.deepEqual(executor.started, []);
	assert.deepEqual(
		outcome.slots.map((s) => s.status),
		["aborted", "aborted"],
	);
});

test("captures a start exception, keeps other results, and waits for all workers", async () => {
	const executor = new FakeExecutor();
	const tasks = [planned(0), planned(1), planned(2)];
	const throwingExecutor: TaskExecutor<FakeResult> = {
		start(spec, report) {
			if (spec.id === "task-2") throw new Error("boom: cannot start");
			return executor.start(spec, report);
		},
		abortedResult: (spec, reason) => executor.abortedResult(spec, reason),
	};

	const outcomePromise = runTaskBatch<FakeResult>({
		tasks,
		concurrency: 2,
		executor: throwingExecutor,
	});
	await flush();
	executor.settle("task-1", "completed", "one");
	await flush();
	executor.settle("task-3", "completed", "three");
	const outcome = await outcomePromise;

	assert.equal(outcome.errors.length, 1);
	assert.match(String((outcome.errors[0] as Error).message), /boom/);
	assert.deepEqual(
		outcome.slots.map((s) => [s.id, s.status, s.result?.label]),
		[
			["task-1", "completed", "one"],
			["task-2", "failed", undefined],
			["task-3", "completed", "three"],
		],
	);
});

test("captures a rejected handle, records failure, and preserves completed results", async () => {
	const executor = new FakeExecutor();
	const outcomePromise = runTaskBatch<FakeResult>({
		tasks: [planned(0), planned(1)],
		concurrency: 2,
		executor,
	});
	await flush();
	executor.settle("task-1", "completed", "one");
	executor.rejectWith("task-2", new Error("child crashed"));

	const outcome = await outcomePromise;
	assert.equal(outcome.errors.length, 1);
	assert.deepEqual(
		outcome.slots.map((s) => [s.id, s.status, s.result?.label]),
		[
			["task-1", "completed", "one"],
			["task-2", "failed", undefined],
		],
	);
});

test("observer callback errors are collected without rejecting or abandoning work", async () => {
	const executor = new FakeExecutor();
	const outcomePromise = runTaskBatch<FakeResult>({
		tasks: [planned(0)],
		concurrency: 1,
		executor,
		onUpdate: () => {
			throw new Error("update observer failed");
		},
		onSettled: () => {
			throw new Error("settled observer failed");
		},
	});

	await flush();
	executor.settle("task-1", "completed");
	const outcome = await outcomePromise;
	assert.equal(outcome.slots[0].status, "completed");
	assert.ok(outcome.errors.some((error) => String(error).includes("update observer failed")));
	assert.ok(outcome.errors.some((error) => String(error).includes("settled observer failed")));
});

test("cancellation with concurrency one aborts the queue and waits for the running task", async () => {
	const executor = new FakeExecutor();
	const controller = new AbortController();
	const tasks = [planned(0), planned(1)];
	const outcomePromise = runTaskBatch<FakeResult>({
		tasks,
		concurrency: 1,
		executor,
		signal: controller.signal,
	});

	await flush();
	assert.deepEqual(executor.started, ["task-1"]);
	controller.abort();
	await flush();
	assert.equal(executor.states.get("task-1")?.terminated, true);
	executor.settle("task-1", "aborted");
	const outcome = await outcomePromise;

	assert.deepEqual(executor.started, ["task-1"]);
	assert.deepEqual(
		outcome.slots.map((s) => s.status),
		["aborted", "aborted"],
	);
});