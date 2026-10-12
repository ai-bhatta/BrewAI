import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from ai_service import BrewAIService
from schemas import (
    EvaluationRequest,
    EvaluationResponse,
    InterpretationRequest,
    InterpretationResponse,
    LabCompareRequest,
    LabCompareResponse,
    LabExamplesResponse,
    LabSummaryResponse,
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    FeedbackItem,
    FeedbackListResponse,
    AnalyticsEventRequest,
    AnalyticsConfigurationResponse,
    AnalyticsSummaryResponse,
    AnalyticsExperimentsResponse,
    BanditDecisionRequest,
    BanditOutcomeRequest,
    CustomerGenerationRequest,
    CustomerGenerationCompareRequest,
)
from feedback_repository import DuplicateFeedbackError
from feedback_service import FeedbackService, FeedbackValidationError
from analytics_service import AnalyticsService, AnalyticsValidationError
from bandit_service import BanditService
from customer_generation_service import CustomerGenerationService, validate_customer_request

app = FastAPI(title="BrewAI API", version="1.0.0")
service = BrewAIService()
feedback_service = FeedbackService()
analytics_service = AnalyticsService()
bandit_service = BanditService()
customer_generation_service = CustomerGenerationService()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_loaded": service.model_loaded,
        "production_model": (service.model_bundle or {}).get("model_name", "heuristic-backup"),
        "production_metadata_available": (service.model_bundle or {}).get("training_metadata") is not None,
        "model_load_error": service.model_load_error,
    }


@app.post("/api/order/interpret", response_model=InterpretationResponse)
def interpret_order(payload: InterpretationRequest) -> InterpretationResponse:
    persona_metadata = {
        "persona": payload.persona,
        "display_name": payload.display_name,
        "character_label": payload.character_label,
        "patience": payload.patience,
        "verbosity": payload.verbosity,
        "ambiguity": payload.ambiguity,
        "coffee_knowledge": payload.coffee_knowledge,
        "preferred_wording": payload.preferred_wording,
    }
    return service.interpret_order(payload.customer_name, payload.request, persona_metadata)


@app.post("/api/order/evaluate", response_model=EvaluationResponse)
def evaluate_order(payload: EvaluationRequest) -> EvaluationResponse:
    return service.evaluate_order(
        payload.ground_truth_recipe,
        payload.predicted_recipe,
        payload.submitted_recipe,
    )


@app.post("/api/lab/compare", response_model=LabCompareResponse)
def compare_lab_models(payload: LabCompareRequest) -> LabCompareResponse:
    try:
        result = service.compare_lab_request(payload.text, payload.ground_truth)
        return LabCompareResponse(**result)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/lab/summary", response_model=LabSummaryResponse)
def lab_summary() -> LabSummaryResponse:
    return LabSummaryResponse(**service.load_lab_summary())


@app.get("/api/lab/examples", response_model=LabExamplesResponse)
def lab_examples() -> LabExamplesResponse:
    try:
        return LabExamplesResponse(**service.load_lab_examples())
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail=f"Robustness examples are unavailable: {error}") from error


@app.post("/api/feedback", response_model=FeedbackCreateResponse, status_code=201)
def submit_feedback(payload: FeedbackCreateRequest) -> FeedbackCreateResponse:
    try:
        return FeedbackCreateResponse(**feedback_service.submit(payload.model_dump()))
    except FeedbackValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DuplicateFeedbackError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=f"Feedback storage is unavailable: {error}") from error


@app.get("/api/feedback", response_model=FeedbackListResponse)
def list_feedback(status: str | None = Query(default="pending")) -> FeedbackListResponse:
    try:
        return FeedbackListResponse(entries=feedback_service.list_entries(status))
    except FeedbackValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=f"Feedback storage is unavailable: {error}") from error


@app.post("/api/feedback/{feedback_id}/approve", response_model=FeedbackItem)
def approve_feedback(feedback_id: str) -> FeedbackItem:
    return review_feedback(feedback_id, "approved")


@app.post("/api/feedback/{feedback_id}/reject", response_model=FeedbackItem)
def reject_feedback(feedback_id: str) -> FeedbackItem:
    return review_feedback(feedback_id, "rejected")


def review_feedback(feedback_id: str, decision: str) -> FeedbackItem:
    try:
        result = feedback_service.review(feedback_id, decision)
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=f"Feedback storage is unavailable: {error}") from error
    if result is None:
        raise HTTPException(status_code=404, detail="Pending feedback entry was not found.")
    return FeedbackItem(**result)


@app.post("/api/analytics/event", status_code=202)
def record_analytics_event(payload: AnalyticsEventRequest) -> dict:
    try:
        analytics_service.record_event(payload.model_dump())
        return {"accepted": True}
    except AnalyticsValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Local analytics storage is unavailable.") from error


@app.get("/api/analytics/config", response_model=AnalyticsConfigurationResponse)
def analytics_config(session_id: str) -> AnalyticsConfigurationResponse:
    try:
        return AnalyticsConfigurationResponse(**analytics_service.configuration_for_session(session_id))
    except AnalyticsValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=f"Local experiment configuration is unavailable: {error}") from error


@app.get("/api/analytics/summary", response_model=AnalyticsSummaryResponse)
def analytics_summary() -> AnalyticsSummaryResponse:
    try:
        return AnalyticsSummaryResponse(**analytics_service.summary())
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Local analytics storage is unavailable.") from error


@app.get("/api/analytics/experiments", response_model=AnalyticsExperimentsResponse)
def analytics_experiments() -> AnalyticsExperimentsResponse:
    try:
        return AnalyticsExperimentsResponse(**analytics_service.experiments())
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=f"Experiment analytics are unavailable: {error}") from error


@app.get("/api/analytics/export")
def export_analytics(format: str = "csv") -> Response:
    try:
        content, media_type = analytics_service.export(format)
        extension = "csv" if format == "csv" else "json"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename=brewai-analytics.{extension}"},
        )
    except AnalyticsValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Local analytics storage is unavailable.") from error


@app.post("/api/analytics/reset")
def reset_analytics() -> dict:
    try:
        analytics_service.repository.reset()
        return {"reset": True}
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Local analytics storage is unavailable.") from error


@app.post("/api/bandit/decision")
def bandit_decision(payload: BanditDecisionRequest) -> dict:
    try:
        return bandit_service.decide(payload.model_dump())
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="Local adaptive policy is unavailable.") from error


@app.post("/api/bandit/outcome")
def bandit_outcome(payload: BanditOutcomeRequest) -> dict:
    try:
        return bandit_service.complete(payload.model_dump())
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="Local adaptive policy update failed.") from error


@app.get("/api/bandit/metrics")
def bandit_metrics() -> dict:
    try:
        return bandit_service.metrics()
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Local adaptive policy metrics are unavailable.") from error


@app.post("/api/bandit/reset")
def reset_bandit() -> dict:
    try:
        bandit_service.reset()
        return {"reset": True}
    except sqlite3.Error as error:
        raise HTTPException(status_code=503, detail="Local adaptive policy reset failed.") from error


@app.get("/api/customer-generation/config")
def customer_generation_config() -> dict:
    try:
        config = customer_generation_service.config()
        return {key: config[key] for key in ("enabled", "mode", "model", "timeout_seconds", "maximum_request_characters")}
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Local customer-generation configuration is unavailable.") from error


@app.post("/api/customer-generation/generate")
async def generate_customer_dialogue(payload: CustomerGenerationRequest) -> dict:
    try:
        return await customer_generation_service.generate(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="Local dialogue generation is unavailable.") from error


@app.post("/api/customer-generation/compare")
async def compare_customer_dialogue(payload: CustomerGenerationCompareRequest) -> dict:
    try:
        recipe, _persona = customer_generation_service._validate_payload(payload.model_dump())
        template = payload.template_request
        template_validation = validate_customer_request(template, recipe)
        local = await customer_generation_service.generate({**payload.model_dump(), "mode": "local_ai"})
        return {"template": {"request": template, "source": "template", "validation": template_validation},
                "local_ai": local}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail="Local dialogue comparison is unavailable.") from error
