# Step 4 API integration plan and coverage audit

Base verified locally and on origin: d63547de128482fdca3a01676273be002fd10faf. Implement on v1.4-step4-api-integration, never old main. Native Linux acceptance is explicitly deferred debt per the current user instruction, not a local-API blocker.

Existing coverage:
- test_api_contract.py uses stub services; strong route/status contracts, no real CRUD/store proof.
- test_service_reliability.py covers transport/error/log/privacy boundaries and TestClient behavior, mostly stub service calls.
- verify_step3_local.py starts the real app with a controlled upstream, verifies health/chat/errors and one upload; lacks full CRUD, index queries, tool execution, 500 filesystem fault and auditable per-request expected/actual evidence.

Chosen minimum additions:
1. A reusable deterministic HTTP model fixture with content-dependent vectors and scripted multi-round tool responses, explicitly marked simulated.
2. One real-Uvicorn runner for API→Service→Agent/tools→Embedding→Chroma. Stop API before each separate store-probe process; inspect real records/query results after upload/update/delete, then restart. No concurrently opened embedded clients and no user data.
3. Record each request method/route template/status/expected status/server request ID, assertions, sanitized log checks, source/environment identities and cleanup. Exceptions or cleanup failures must retain failed evidence, never overwrite history.
4. Add automated subprocess integration tests using the same runner, plus harness safety/failure tests. Reuse old unit and TestClient coverage rather than duplicating every matrix entry.
5. Real Ollama is optional and separate: verify existing tags, minimal chat/embedding and fresh-document retrieval only if available. Never download models. Docker gets one config/Engine check and, only if available, dedicated fresh-data container testing; no repairs.
6. Run target/full regression, independent read-only code review, produce step4-source-handoff.md, commit exact files and safely push only the new development branch. Do not merge, tag or alter earlier evidence.

Mandatory core: six routes, full CRUD plus direct persisted-store inspection, retrieval after update/deletion, actual calculator/search tool loop, validation and 400/404/422/502/503/504/500, request/log privacy and child/temp cleanup. Optional real Ollama, Docker and native Linux have distinct statuses.
