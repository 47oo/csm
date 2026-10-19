/**
 * Offline tests for the child-process termination primitive.
 *
 * Run with:  node --test .pi/extensions/subagent/*.test.ts
 */

import { spawn } from "node:child_process";
import { EventEmitter } from "node:events";
import assert from "node:assert/strict";
import { test } from "node:test";
import { manageTermination } from "./proc-manager.ts";

class FakeProcess extends EventEmitter {
	pid: number | undefined;
	signals: NodeJS.Signals[] = [];

	constructor(pid: number | undefined = 4242) {
		super();
		this.pid = pid;
	}

	kill(signal?: NodeJS.Signals): boolean {
		this.signals.push(signal ?? "SIGTERM");
		return true;
	}

	close(): void {
		this.emit("close", 0, null);
	}
}

function manualTimers() {
	const pending = new Map<number, () => void>();
	let nextId = 0;
	return {
		setTimer: (fn: () => void, _ms: number) => {
			const id = ++nextId as unknown as ReturnType<typeof setTimeout>;
			pending.set(id as unknown as number, fn);
			return id;
		},
		clearTimer: (timer: ReturnType<typeof setTimeout>) => {
			pending.delete(timer as unknown as number);
		},
		fireAll: () => {
			const callbacks = [...pending.values()];
			pending.clear();
			for (const cb of callbacks) cb();
		},
		size: () => pending.size,
	};
}

test("sends SIGTERM to the POSIX process group and waits for close", async () => {
	const proc = new FakeProcess(1234);
	const groups: Array<{ pgid: number; signal: NodeJS.Signals }> = [];
	const timers = manualTimers();
	const controller = manageTermination(proc, {
		platform: "linux",
		killProcessGroup: (pgid, signal) => groups.push({ pgid, signal }),
		setTimer: timers.setTimer,
		clearTimer: timers.clearTimer,
	});

	let closed = false;
	controller.closed.then(() => {
		closed = true;
	});

	controller.terminate();
	controller.terminate(); // idempotent
	assert.deepEqual(groups, [{ pgid: -1234, signal: "SIGTERM" }]);
	assert.equal(controller.signalSent, "SIGTERM");
	assert.equal(closed, false, "must not be considered closed before the close event");

	proc.close();
	await controller.closed;
	assert.equal(closed, true);
	assert.equal(timers.size(), 0, "grace timer must be cleared on close");

	// Firing the (cleared) timer must not force-kill a closed process.
	timers.fireAll();
	assert.deepEqual(groups, [{ pgid: -1234, signal: "SIGTERM" }]);
});

test("escalates to SIGKILL only after the grace period and before close", async () => {
	const proc = new FakeProcess(99);
	const groups: Array<{ pgid: number; signal: NodeJS.Signals }> = [];
	const timers = manualTimers();
	const controller = manageTermination(proc, {
		platform: "darwin",
		graceMs: 1000,
		killProcessGroup: (pgid, signal) => groups.push({ pgid, signal }),
		setTimer: timers.setTimer,
		clearTimer: timers.clearTimer,
	});

	controller.terminate();
	assert.deepEqual(groups, [{ pgid: -99, signal: "SIGTERM" }]);

	timers.fireAll();
	assert.deepEqual(groups, [
		{ pgid: -99, signal: "SIGTERM" },
		{ pgid: -99, signal: "SIGKILL" },
	]);
	assert.equal(controller.signalSent, "SIGKILL");

	proc.close();
	await controller.closed;
});

test("falls back to signalling the direct child when group kill fails", async () => {
	const proc = new FakeProcess(7);
	const timers = manualTimers();
	const controller = manageTermination(proc, {
		platform: "linux",
		killProcessGroup: () => {
			throw new Error("ESRCH");
		},
		setTimer: timers.setTimer,
		clearTimer: timers.clearTimer,
	});

	controller.terminate();
	assert.deepEqual(proc.signals, ["SIGTERM"]);
	proc.close();
	await controller.closed;
});

test("uses child.kill on Windows and never a process group", async () => {
	const proc = new FakeProcess(500);
	let groupCalls = 0;
	const timers = manualTimers();
	const controller = manageTermination(proc, {
		platform: "win32",
		killProcessGroup: () => {
			groupCalls += 1;
		},
		setTimer: timers.setTimer,
		clearTimer: timers.clearTimer,
	});

	controller.terminate();
	assert.equal(groupCalls, 0);
	assert.deepEqual(proc.signals, ["SIGTERM"]);
	proc.close();
	await controller.closed;
});

test("terminate after close is a no-op and does not leak a timer", async () => {
	const proc = new FakeProcess(11);
	const groups: NodeJS.Signals[] = [];
	const timers = manualTimers();
	const controller = manageTermination(proc, {
		platform: "linux",
		killProcessGroup: (_pgid, signal) => groups.push(signal),
		setTimer: timers.setTimer,
		clearTimer: timers.clearTimer,
	});

	proc.close();
	await controller.closed;
	controller.terminate();
	assert.deepEqual(groups, []);
	assert.equal(timers.size(), 0);
});

test(
	"escalates and reaps a real detached POSIX child that ignores SIGTERM",
	{ skip: process.platform === "win32", timeout: 5000 },
	async () => {
		const proc = spawn(
			process.execPath,
			[
				"-e",
				'process.on("SIGTERM", () => {}); if (process.send) process.send("ready"); setInterval(() => {}, 1000);',
			],
			{ detached: true, stdio: ["ignore", "ignore", "ignore", "ipc"] },
		);
		const ready = new Promise<void>((resolve, reject) => {
			proc.once("message", () => resolve());
			proc.once("error", reject);
		});
		await ready;

		const controller = manageTermination(proc, { graceMs: 50 });
		try {
			controller.terminate();
			await controller.closed;
			assert.equal(controller.signalSent, "SIGKILL");
		} finally {
			if (proc.exitCode === null && proc.pid) {
				try {
					process.kill(-proc.pid, "SIGKILL");
				} catch {
					proc.kill("SIGKILL");
				}
			}
		}
	},
);