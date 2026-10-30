"""Independent workflow API. Existing chat service remains unchanged."""
from fastapi import APIRouter
from knowledge_pilot.workflow.schemas import WorkflowRequest, WorkflowResponse

router = APIRouter()


@router.post('/workflow/chat', response_model=WorkflowResponse, response_model_exclude_unset=True, responses={
    502: {'description': 'Invalid model response'},
    503: {'description': 'Model unavailable'},
    504: {'description': 'Model timeout'},
})
def workflow_chat(request: WorkflowRequest):
    from knowledge_pilot.workflow.graph import run_workflow
    from knowledge_pilot.api.sessions import session_http
    return session_http(lambda: run_workflow(request))
