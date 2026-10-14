/**
 * Task planning for the subagent extension.
 *
 * Resolves stable task IDs and validates optional task declarations
 * (`id`, `writeScope`, `resources`) *before* any child process is started.
 *
 * A declaration is cooperative batch-scheduling metadata only. It is not a
 * sandbox: it neither restricts filesystem access nor isolates OS resources.
 * Conflicting declarations are rejected so that a parallel batch is either
 * planned and started as a whole or not started at all.
 *
 * This module deliberately has no dependency on `@earendil-works/pi-*` so it
 * can be exercised offline with `node --test`.
 */

import * as fs from "node:fs";
import * as path from "node:path";

/** Explicit lifecycle for a single task. */
export type TaskStatus = "queued" | "running" | "completed" | "failed" | "aborted";

export const MAX_DECLARED_ID_LENGTH = 64;
export const MAX_RESOURCE_NAME_LENGTH = 64;

export interface RawTaskDeclaration {
	/** Optional caller-provided stable identifier, unique within one batch. */
	id?: string;
	/** Relative file or directory paths (no globs) the task intends to write. */
	writeScope?: string[];
	/** Exclusive resource names held by the task for the duration of the batch. */
	resources?: string[];
}

export interface TaskPlanningInput extends RawTaskDeclaration {
	agent: string;
	task: string;
	cwd?: string;
}

export interface PlannedTask {
	index: number;
	id: string;
	/** True when the id came from the caller rather than being generated. */
	idProvided: boolean;
	/** True when the caller supplied at least one declaration field. */
	declared: boolean;
	agent: string;
	task: string;
	/** Absolute working directory the child process is started in. */
	cwd: string;
	/** writeScope exactly as declared, kept for reporting. */
	rawWriteScope: string[];
	/** writeScope normalized to absolute, symlink-resolved paths. */
	writeScope: string[];
	resources: string[];
}

export type DeclarationConflictKind =
	| "duplicate-id"
	| "invalid-id"
	| "invalid-write-scope"
	| "write-scope-overlap"
	| "invalid-resource"
	| "resource-conflict";

export interface DeclarationConflict {
	kind: DeclarationConflictKind;
	message: string;
	taskIds: string[];
}

export interface TaskPlanningResult {
	tasks: PlannedTask[];
	conflicts: DeclarationConflict[];
}

/**
 * Resolve a path to an absolute canonical path, following symlinks on the
 * nearest existing ancestor. Paths that do not exist yet (for example a file
 * about to be created) are normalized against the realpath of their existing
 * parent, so a symlinked directory is handled where the OS allows it.
 */
export function realpathBestEffort(target: string): string {
	const fallback = path.resolve(target);
	let current = fallback;
	const trailing: string[] = [];

	while (true) {
		try {
			const real = fs.realpathSync(current);
			return trailing.length > 0 ? path.join(real, ...trailing.slice().reverse()) : real;
		} catch {
			const parent = path.dirname(current);
			if (parent === current) return fallback;
			trailing.push(path.basename(current));
			current = parent;
		}
	}
}

/** Normalize a declared write path (relative to `baseDir`) to an absolute path. */
export function normalizeWriteScope(declared: string, baseDir: string): string {
	return realpathBestEffort(path.resolve(baseDir, declared));
}

/**
 * Path overlap uses segment boundaries, so `/a/b` and `/a/bc` do not overlap,
 * while `/a/b` and `/a/b/c` do. Used for both files and directories.
 */
export function pathsOverlap(a: string, b: string): boolean {
	if (a === b) return true;
	const sep = path.sep;
	return a.startsWith(b + sep) || b.startsWith(a + sep);
}

const CREDENTIAL_MARKERS =
	/(secret|password|passwd|passphrase|token|api[-_]?key|apikey|bearer|credential|private[-_]?key|access[-_]?key)/i;
const OPAQUE_TOKEN = /^[A-Za-z0-9+/=_-]+$/;

/**
 * Reject resource names that plausibly embed credentials. This is a heuristic
 * guard, not a security boundary: resource names are advisory metadata.
 */
export function resourceNameError(name: string): string | null {
	if (typeof name !== "string" || name.trim() === "") {
		return "resource name must be a non-empty string";
	}
	if (name !== name.trim()) {
		return "resource name must not have leading or trailing whitespace";
	}
	if (/[\s\u0000-\u001f]/.test(name)) {
		return "resource name must not contain whitespace or control characters";
	}
	if (name.length > MAX_RESOURCE_NAME_LENGTH) {
		return `resource name must be at most ${MAX_RESOURCE_NAME_LENGTH} characters`;
	}
	if (CREDENTIAL_MARKERS.test(name)) {
		return "resource name looks like it may contain a credential; do not embed secrets in resource names";
	}
	if (name.includes("=") || name.includes("://")) {
		return "resource name must not contain '=' or '://'";
	}
	const looksOpaque =
		name.length >= 32 &&
		OPAQUE_TOKEN.test(name) &&
		/[A-Z]/.test(name) &&
		/[a-z]/.test(name) &&
		/[0-9]/.test(name);
	if (looksOpaque) {
		return "resource name looks like an opaque token; use a short human-readable name";
	}
	return null;
}

function declaredIdError(id: string): string | null {
	if (id.trim() === "") return "task id must be a non-empty string";
	if (id !== id.trim()) return "task id must not have leading or trailing whitespace";
	if (/[\s\u0000-\u001f]/.test(id)) return "task id must not contain whitespace or control characters";
	if (id.length > MAX_DECLARED_ID_LENGTH) return `task id must be at most ${MAX_DECLARED_ID_LENGTH} characters`;
	return null;
}

function writeScopeError(declared: string): string | null {
	if (typeof declared !== "string" || declared.trim() === "") return "writeScope entries must be non-empty strings";
	if (path.isAbsolute(declared)) return "writeScope entries must be relative to the task working directory";
	if (/[*?[\]{}!]/.test(declared)) return "writeScope entries must be literal paths, not glob patterns";
	return null;
}

function generatedId(index: number, taken: Set<string>): string {
	let candidate = `task-${index + 1}`;
	let suffix = 1;
	while (taken.has(candidate)) {
		suffix += 1;
		candidate = `task-${index + 1}-${suffix}`;
	}
	return candidate;
}

/**
 * Resolve IDs and detect declaration conflicts for one batch.
 *
 * Conflicts are returned rather than thrown so callers can render them. When
 * `conflicts` is non-empty the caller must not start any task.
 */
export function planTasks(inputs: TaskPlanningInput[], baseDir: string): TaskPlanningResult {
	const conflicts: DeclarationConflict[] = [];
	const declaredIds = new Map<string, number>();
	const idForIndex: string[] = [];

	// First pass: resolve IDs and surface duplicate/invalid declared IDs.
	for (let i = 0; i < inputs.length; i++) {
		const input = inputs[i];
		const provided = typeof input.id === "string" && input.id.trim() !== "";
		if (provided) {
			const err = declaredIdError(input.id as string);
			if (err) {
				conflicts.push({ kind: "invalid-id", message: `Task ${i + 1}: ${err}`, taskIds: [] });
			}
			const existing = declaredIds.get(input.id as string);
			if (existing !== undefined) {
				conflicts.push({
					kind: "duplicate-id",
					message: `Duplicate task id ${JSON.stringify(input.id)} (tasks ${existing + 1} and ${i + 1}).`,
					taskIds: [input.id as string],
				});
			} else {
				declaredIds.set(input.id as string, i);
			}
		}
		idForIndex.push(provided ? (input.id as string) : "");
	}

	const taken = new Set<string>(declaredIds.keys());
	for (let i = 0; i < idForIndex.length; i++) {
		if (idForIndex[i] === "") idForIndex[i] = generatedId(i, taken);
		taken.add(idForIndex[i]);
	}

	// Second pass: build planned tasks and validate declarations.
	const tasks: PlannedTask[] = [];
	for (let i = 0; i < inputs.length; i++) {
		const input = inputs[i];
		const cwd = path.resolve(baseDir, input.cwd ?? ".");
		const rawWriteScope = input.writeScope ?? [];
		const resources = input.resources ?? [];
		const declared =
			(typeof input.id === "string" && input.id.trim() !== "") ||
			rawWriteScope.length > 0 ||
			resources.length > 0;

		const writeScope: string[] = [];
		for (const entry of rawWriteScope) {
			const err = writeScopeError(entry);
			if (err) {
				conflicts.push({
					kind: "invalid-write-scope",
					message: `Task ${idForIndex[i]}: ${err} (${JSON.stringify(entry)})`,
					taskIds: [idForIndex[i]],
				});
				continue;
			}
			writeScope.push(normalizeWriteScope(entry, cwd));
		}

		for (const name of resources) {
			const err = resourceNameError(name);
			if (err) {
				conflicts.push({
					kind: "invalid-resource",
					message: `Task ${idForIndex[i]}: ${err}`,
					taskIds: [idForIndex[i]],
				});
			}
		}

		tasks.push({
			index: i,
			id: idForIndex[i],
			idProvided: idForIndex[i] === input.id,
			declared,
			agent: input.agent,
			task: input.task,
			cwd,
			rawWriteScope,
			writeScope,
			resources,
		});
	}

	// Pairwise checks for write scope and exclusive resources.
	for (let a = 0; a < tasks.length; a++) {
		for (let b = a + 1; b < tasks.length; b++) {
			for (const pa of tasks[a].writeScope) {
				for (const pb of tasks[b].writeScope) {
					if (pathsOverlap(pa, pb)) {
						conflicts.push({
							kind: "write-scope-overlap",
							message: `Tasks ${tasks[a].id} and ${tasks[b].id} declare overlapping writeScope (${pa} overlaps ${pb}).`,
							taskIds: [tasks[a].id, tasks[b].id],
						});
					}
				}
			}
			for (const ra of tasks[a].resources) {
				for (const rb of tasks[b].resources) {
					if (ra === rb) {
						conflicts.push({
							kind: "resource-conflict",
							message: `Tasks ${tasks[a].id} and ${tasks[b].id} both declare exclusive resource ${JSON.stringify(ra)}.`,
							taskIds: [tasks[a].id, tasks[b].id],
						});
					}
				}
			}
		}
	}

	return { tasks, conflicts };
}

export interface ActiveDeclarations {
	ownerId: string;
	resources: Array<{ name: string; taskId: string }>;
	writeScopes: Array<{ path: string; taskId: string }>;
}

/**
 * Tracks declarations of in-flight batches *within a single Pi process* so
 * that two `subagent` tool executions running concurrently do not start
 * conflicting work. It provides no isolation across separate Pi processes.
 */
export class ActiveDeclarationRegistry {
	private entries = new Map<string, ActiveDeclarations>();

	/** Register a batch. Returns cross-batch conflicts; nothing is stored when conflicts exist. */
	register(entry: ActiveDeclarations): DeclarationConflict[] {
		const conflicts: DeclarationConflict[] = [];
		for (const other of this.entries.values()) {
			if (other.ownerId === entry.ownerId) continue;
			for (const r of entry.resources) {
				for (const o of other.resources) {
					if (r.name === o.name) {
						conflicts.push({
							kind: "resource-conflict",
							message: `Resource ${JSON.stringify(r.name)} is already held by an in-flight batch (${o.taskId}).`,
							taskIds: [r.taskId],
						});
					}
				}
			}
			for (const a of entry.writeScopes) {
				for (const b of other.writeScopes) {
					if (pathsOverlap(a.path, b.path)) {
						conflicts.push({
							kind: "write-scope-overlap",
							message: `writeScope ${a.path} overlaps an in-flight batch (${b.taskId}: ${b.path}).`,
							taskIds: [a.taskId],
						});
					}
				}
			}
		}
		if (conflicts.length === 0) this.entries.set(entry.ownerId, entry);
		return conflicts;
	}

	release(ownerId: string): void {
		this.entries.delete(ownerId);
	}

	get activeOwners(): number {
		return this.entries.size;
	}

	clear(): void {
		this.entries.clear();
	}
}

/** Process-wide registry used by the extension. */
export const sharedDeclarationRegistry = new ActiveDeclarationRegistry();