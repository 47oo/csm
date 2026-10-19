/**
 * Offline tests for task planning and declaration conflict detection.
 *
 * Run with:  node --test .pi/extensions/subagent/*.test.ts
 */

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import {
	ActiveDeclarationRegistry,
	normalizeWriteScope,
	pathsOverlap,
	planTasks,
	realpathBestEffort,
	resourceNameError,
	type TaskPlanningInput,
} from "./task-plan.ts";

function input(overrides: Partial<TaskPlanningInput> & { agent?: string; task?: string }): TaskPlanningInput {
	return { agent: "worker", task: "work", ...overrides };
}

test("generates stable unique ids and allows the same agent more than once", () => {
	const { tasks, conflicts } = planTasks(
		[input({}), input({ agent: "worker" }), input({ agent: "worker" })],
		"/tmp",
	);
	assert.deepEqual(conflicts, []);
	assert.deepEqual(
		tasks.map((t) => t.id),
		["task-1", "task-2", "task-3"],
	);
	assert.equal(tasks.every((t) => t.declared === false), true);
});

test("uses declared ids and reports duplicates and invalid ids before starting", () => {
	const { tasks, conflicts } = planTasks(
		[
			input({ id: "alpha" }),
			input({ id: "beta" }),
			input({ id: "alpha" }),
			input({ id: "bad id" }),
		],
		"/tmp",
	);
	assert.deepEqual(
		tasks.map((t) => t.id),
		["alpha", "beta", "alpha", "bad id"],
	);
	assert.ok(conflicts.some((c) => c.kind === "duplicate-id"));
	assert.ok(conflicts.some((c) => c.kind === "invalid-id"));
});

test("declared ids do not silently collide with generated ids", () => {
	const { tasks, conflicts } = planTasks([input({ id: "task-1" }), input({})], "/tmp");
	assert.deepEqual(conflicts, []);
	assert.deepEqual(
		tasks.map((t) => t.id),
		["task-1", "task-2"],
	);
});

test("path overlap uses segment boundaries", () => {
	assert.equal(pathsOverlap("/a/b", "/a/b"), true);
	assert.equal(pathsOverlap("/a/b", "/a/b/c"), true);
	assert.equal(pathsOverlap("/a/b/c", "/a/b"), true);
	assert.equal(pathsOverlap("/a/b", "/a/bc"), false);
	assert.equal(pathsOverlap("/a/b", "/a/c"), false);
});

test("detects overlapping write scopes and same exclusive resources", () => {
	const { conflicts } = planTasks(
		[
			input({ id: "a", writeScope: ["src"], resources: ["gpu:0"] }),
			input({ id: "b", writeScope: ["src/lib"], resources: ["gpu:0"] }),
			input({ id: "c", writeScope: ["docs"] }),
		],
		"/repo",
	);
	assert.ok(conflicts.some((c) => c.kind === "write-scope-overlap" && c.taskIds.includes("a") && c.taskIds.includes("b")));
	assert.ok(conflicts.some((c) => c.kind === "resource-conflict" && c.taskIds.includes("a") && c.taskIds.includes("b")));
});

test("non-overlapping declarations produce no conflicts", () => {
	const { conflicts } = planTasks(
		[
			input({ id: "a", writeScope: ["src/a"], resources: ["gpu:0"] }),
			input({ id: "b", writeScope: ["src/b"], resources: ["gpu:1"] }),
		],
		"/repo",
	);
	assert.deepEqual(conflicts, []);
});

test("resolves symlinked write scope directories to their canonical target", () => {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "subagent-plan-"));
	try {
		const realDir = path.join(root, "real");
		fs.mkdirSync(realDir);
		const linkDir = path.join(root, "link");
		fs.symlinkSync(realDir, linkDir, "dir");

		const viaLink = normalizeWriteScope("out.txt", linkDir);
		const viaReal = normalizeWriteScope("out.txt", realDir);
		assert.equal(viaLink, viaReal, "symlinked ancestors must normalize to the same path");

		const { conflicts } = planTasks(
			[
				input({ id: "a", cwd: linkDir, writeScope: ["out.txt"] }),
				input({ id: "b", cwd: realDir, writeScope: ["out.txt"] }),
			],
			root,
		);
		assert.ok(
			conflicts.some((c) => c.kind === "write-scope-overlap"),
			"same file reached through a symlink must be detected as overlap",
		);
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
});

test("realpathBestEffort resolves the nearest existing ancestor for new paths", () => {
	const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "subagent-real-")));
	try {
		const nested = path.join(root, "a", "b", "new.txt");
		assert.equal(realpathBestEffort(nested), path.join(root, "a", "b", "new.txt"));
	} finally {
		fs.rmSync(root, { recursive: true, force: true });
	}
});

test("rejects absolute paths and glob patterns in writeScope", () => {
	const { conflicts } = planTasks(
		[input({ writeScope: ["/etc/passwd"] }), input({ writeScope: ["src/*.ts"] })],
		"/repo",
	);
	assert.equal(conflicts.filter((c) => c.kind === "invalid-write-scope").length, 2);
});

test("rejects resource names that look like credentials", () => {
	assert.equal(resourceNameError("gpu.0"), null);
	assert.equal(resourceNameError("build-cache"), null);
	assert.notEqual(resourceNameError("api_key"), null);
	assert.notEqual(resourceNameError("bearer-abc"), null);
	assert.notEqual(resourceNameError("secret:prod"), null);
	assert.notEqual(resourceNameError("AaBbCcDdEeFf00112233445566778899"), null);
	assert.notEqual(resourceNameError("has space"), null);
	assert.notEqual(resourceNameError("token=abc"), null);
});

test("invalid resource names are reported as conflicts", () => {
	const { conflicts } = planTasks([input({ resources: ["ApiKey=xyz"] })], "/repo");
	assert.ok(conflicts.some((c) => c.kind === "invalid-resource"));
});

test("active registry detects cross-batch resource and write conflicts and releases", () => {
	const registry = new ActiveDeclarationRegistry();
	const first = registry.register({
		ownerId: "batch-1",
		resources: [{ name: "gpu:0", taskId: "task-1" }],
		writeScopes: [{ path: "/repo/src", taskId: "task-1" }],
	});
	assert.deepEqual(first, []);
	assert.equal(registry.activeOwners, 1);

	const clash = registry.register({
		ownerId: "batch-2",
		resources: [{ name: "gpu:0", taskId: "task-1" }],
		writeScopes: [{ path: "/repo/src/lib", taskId: "task-1" }],
	});
	assert.ok(clash.some((c) => c.kind === "resource-conflict"));
	assert.ok(clash.some((c) => c.kind === "write-scope-overlap"));
	assert.equal(registry.activeOwners, 1, "a conflicting batch must not be registered");

	registry.release("batch-1");
	assert.equal(registry.activeOwners, 0);
	const after = registry.register({
		ownerId: "batch-3",
		resources: [{ name: "gpu:0", taskId: "task-1" }],
		writeScopes: [],
	});
	assert.deepEqual(after, []);
});