"""Independent workflow API. Existing chat service remains unchanged."""
from fastapi import APIRouter
from knowledge_pilot.workflow.schemas import WorkflowRequest, WorkflowResponse

router = APIRouter()


@router.post('/workflow/chat', response_model=WorkflowResponse, responses={
    502: {'description': 'Invalid model response'},
    503: {'description': 'Model unavailable'},
    504: {'description': 'Model timeout'},
})
def workflow_chat(request: WorkflowRequest):
    from knowledge_pilot.workflow.graph import run_workflow
    return run_workflow(request)
