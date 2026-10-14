/**
 * Child-process termination primitive for the subagent extension.
 *
 * The important guarantee is that completion is decided by the process's
 * actual `close` event, never by `child.killed` (which only records that a
 * signal was sent, not that the process exited).
 *
 * On POSIX, children are started as their own process-group leader, so a
 * SIGTERM/SIGKILL can be delivered to the whole group. That stops shells
 * waiting on grandchildren (`bash -c "...; long-cmd"`). Windows has no process
 * groups here; only the direct child is signalled.
 *
 * Depends only on Node builtins so it can be tested offline with a fake child.
 */

export interface CloseAwareProcess {
	readonly pid?: number | undefined;
	once(event: string, listener: (...args: any[]) => void): unknown;
	removeListener(event: string, listener: (...args: any[]) => void): unknown;
	kill(signal?: NodeJS.Signals): boolean;
}

export interface TerminationOptions {
	/** Milliseconds between SIGTERM and SIGKILL. Default 5000. */
	graceMs?: number;
	platform?: NodeJS.Platform;
	/** Injectable for tests; defaults to process.kill(-pgid, signal). */
	killProcessGroup?: (pgid: number, signal: NodeJS.Signals) => void;
	/** Injectable timer functions for tests. */
	setTimer?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
	clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
}

export interface TerminationController {
	/** Resolves once the process has actually closed. */
	readonly closed: Promise<void>;
	/** Signal most recently sent, or null when `terminate()` was never called. */
	readonly signalSent: NodeJS.Signals | null;
	/** Idempotent. SIGTERM now, SIGKILL after the grace period if still open. */
	terminate(): void;
}

export function manageTermination(proc: CloseAwareProcess, options: TerminationOptions = {}): TerminationController {
	const graceMs = options.graceMs ?? 5000;
	const platform = options.platform ?? process.platform;
	const killProcessGroup =
		options.killProcessGroup ?? ((pgid: number, signal: NodeJS.Signals) => process.kill(pgid, signal));
	const setTimer = options.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
	const clearTimer = options.clearTimer ?? ((timer) => clearTimeout(timer));

	let closed = false;
	let terminateRequested = false;
	let forced = false;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let resolveClosed!: () => void;
	const closedPromise = new Promise<void>((resolve) => {
		resolveClosed = resolve;
	});

	const onClose = () => {
		if (closed) return;
		closed = true;
		if (timer !== null) {
			clearTimer(timer);
			timer = null;
		}
		proc.removeListener("close", onClose);
		resolveClosed();
	};
	proc.once("close", onClose);

	const send = (signal: NodeJS.Signals) => {
		const pid = proc.pid;
		if (platform !== "win32" && typeof pid === "number" && pid > 0) {
			try {
				killProcessGroup(-pid, signal);
				return;
			} catch {
				// Fall back to signalling only the direct child (e.g. not a group leader).
			}
		}
		try {
			proc.kill(signal);
		} catch {
			// Process already gone; the close event (or its absence) decides.
		}
	};

	const terminate = () => {
		if (terminateRequested || closed) return;
		terminateRequested = true;
		send("SIGTERM");
		if (closed) return;
		timer = setTimer(() => {
			timer = null;
			if (closed) return;
			forced = true;
			send("SIGKILL");
		}, graceMs);
	};

	return {
		closed: closedPromise,
		get signalSent() {
			if (!terminateRequested) return null;
			return forced ? "SIGKILL" : "SIGTERM";
		},
		terminate,
	};
}