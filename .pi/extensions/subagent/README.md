# Project subagent extension

Project-local fork of Pi's subagent example. It delegates work to isolated `pi` child processes and adds cooperative scheduling for parallel writers.

## Modes

- Single: `{ agent, task }`
- Parallel: `{ tasks, concurrency? }`
- Chain: `{ chain }`

The default agent scope is `project`. Set `agentScope: "both"` when user-level agents are also needed.

## Parallel batches

A batch accepts at most 8 tasks and runs 4 concurrently by default. `concurrency` may be set from 1 to 8 for one batch.

Each parallel task may declare:

- `id`: stable identifier within the batch.
- `writeScope`: relative files or directories the task may write.
- `resources`: exclusive names for shared services, ports, test environments, or similar resources.

Overlapping declarations are rejected before any child starts. Declarations are cooperative metadata, not a sandbox: they do not restrict filesystem access. Cross-batch checks cover one Pi process only; separate Pi processes do not share the registry.

On POSIX, child processes run in their own process groups so cancellation can escalate from SIGTERM to SIGKILL and reap descendants. Windows can signal only the direct child through this implementation.

## Workflow constraints

Use parallel mode only inside one already-approved workflow Gate. Product, design finalization, Test, Review, and Merge remain coordinator-validated boundaries; do not use `chain` to bypass them.

Parallel writers must have disjoint `writeScope` declarations. Serialize shared files and complete all writers before Git operations.

## Verification

Run the offline scheduler, declaration, and process tests:

```bash
node --test .pi/extensions/subagent/*.test.ts
```

The process-manager suite includes a real detached-child test on POSIX. Loading the extension through Pi is still required after changing `index.ts` because the offline tests do not instantiate the Pi extension API.
