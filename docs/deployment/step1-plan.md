# V1.4 Step 1 implementation plan

Goal: environment configuration and a minimal Docker deployment of the existing FastAPI service.

Architecture: retain the six API routes, import-time initialization and all retrieval/Agent behavior. Add standard-library environment reads to config.py, feed existing callers, and bind a complete data directory into one API container. Ollama remains on the host. No dependency upgrades or installations on the host, commits, tags or later-step features.

1. Record HEAD, original worktree status and existing interpreter versions; run the existing isolated baseline.
2. Add subprocess-based configuration tests for defaults, environment overrides, invalid values and embedding caller configuration; run them before implementation and record failures.
3. Update config.py and only the configuration references in embedding.py, chroma_store.py and api/services.py. Preserve default relative data paths for existing evaluation CWD isolation.
4. Add .env.example, Dockerfile, .dockerignore and compose.yaml. Install the actual package from pyproject.toml in the image, run knowledge_pilot.api.app:app, bind the whole data root, and configure host.docker.internal.
5. Run targeted tests and the complete offline regression. Probe actual temporary-store API health and persistence using the existing environment, without touching the developer database.
6. Attempt Docker config/build/start/health/network/mount verification if a Docker CLI and daemon exist. Record exact blockers otherwise.
7. Document commands, file responsibilities, evidence and pending checks. Recheck original main status and frozen tracked file contents. Stop after Step 1.
