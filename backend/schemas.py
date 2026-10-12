from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class InterpretationRequest(BaseModel):
    customer_name: str
    request: str
    persona: Optional[str] = None
    display_name: Optional[str] = None
    character_label: Optional[str] = None
    patience: Optional[float] = None
    verbosity: Optional[float] = None
    ambiguity: Optional[float] = None
    coffee_knowledge: Optional[float] = None
    preferred_wording: Optional[List[str]] = None


class InterpretationResponse(BaseModel):
    recipe: Dict[str, str]
    confidence: Dict[str, Optional[float]]
    source: str
    explanation: List[str]
    persona: Optional[str] = None
    display_name: Optional[str] = None
    character_label: Optional[str] = None
    patience: Optional[float] = None
    verbosity: Optional[float] = None
    ambiguity: Optional[float] = None
    coffee_knowledge: Optional[float] = None
    preferred_wording: Optional[List[str]] = None


class EvaluationRequest(BaseModel):
    ground_truth_recipe: Dict[str, str]
    predicted_recipe: Dict[str, str]
    submitted_recipe: Dict[str, str]


class EvaluationResponse(BaseModel):
    ai_matches: int
    player_matches: int
    total_attributes: int
    points_awarded: int
    combo_delta: int
    feedback: str


class LabCompareRequest(BaseModel):
    text: str
    ground_truth: Optional[Dict[str, str]] = None


class LabModelResult(BaseModel):
    prediction: Optional[Dict[str, str]] = None
    confidence: Optional[Dict[str, Optional[float]]] = None
    latency_ms: Optional[float] = None
    available: bool
    error: Optional[str] = None


class LabCompareResponse(BaseModel):
    models: Dict[str, LabModelResult]
    ground_truth: Optional[Dict[str, str]] = None


class LabSummaryResponse(BaseModel):
    benchmark_available: bool
    benchmark_winner: Optional[str] = None
    benchmark_macro_f1: Optional[float] = None
    benchmark_average_latency_ms: Optional[float] = None
    currently_served_model: str
    currently_served_source: str
    production_macro_f1: Optional[float] = None
    production_evaluation: Optional[str] = None
    production_reason: Optional[str] = None
    comparison_model_metadata: Optional[Dict[str, object]] = None
    error: Optional[str] = None


class LabExamplesResponse(BaseModel):
    categories: List[str]
    records: List[Dict[str, str]]


class FeedbackCreateRequest(BaseModel):
    text: str
    model: str
    predicted: Dict[str, str]
    corrected: Dict[str, str]
    confidence: Optional[Dict[str, Optional[float]]] = None
    model_disagreement: bool = False


class FeedbackItem(BaseModel):
    id: str
    text: str
    model: str
    predicted: Dict[str, str]
    corrected: Dict[str, str]
    confidence: Optional[Dict[str, Optional[float]]] = None
    source: str
    status: str
    created_at: str
    reviewed_at: Optional[str] = None
    model_disagreement: bool = False
    low_confidence: bool = False
    priority: int = 3


class FeedbackCreateResponse(BaseModel):
    feedback: FeedbackItem
    similar_entries: List[Dict[str, object]] = Field(default_factory=list)


class FeedbackListResponse(BaseModel):
    entries: List[FeedbackItem]


class FeedbackReviewRequest(BaseModel):
    decision: str


class AnalyticsEventRequest(BaseModel):
    event_name: str
    session_id: str
    player_id: Optional[str] = None
    game_mode: str = "none"
    timestamp: str
    properties: Dict[str, object] = Field(default_factory=dict)


class AnalyticsConfigurationResponse(BaseModel):
    session_id: str
    assignments: Dict[str, str]
    feature_flags: Dict[str, object]
    experiments: Dict[str, object]
    minimum_exploratory_sessions_per_variant: int


class AnalyticsSummaryResponse(BaseModel):
    engagement: Dict[str, object]
    gameplay: Dict[str, object]
    difficulty: Dict[str, object]
    ai_quality: Dict[str, object]
    feedback: Dict[str, object]
    funnel: List[Dict[str, object]]
    events_recorded: int


class AnalyticsExperimentsResponse(BaseModel):
    experiments: Dict[str, object]
    minimum_sessions_per_variant: int


class BanditDecisionRequest(BaseModel):
    session_id: str
    player_id: Optional[str] = None
    current_difficulty: str
    heuristic_action: str
    metrics: Dict[str, float] = Field(default_factory=dict)


class BanditOutcomeRequest(BaseModel):
    decision_id: str
    correct: bool = False
    customer_lost: bool = False
    response_time_seconds: float = 0
    hints_used: int = 0
    clarifications_used: int = 0


class CustomerGenerationRequest(BaseModel):
    canonical_recipe: Dict[str, str]
    persona: Dict[str, object]
    difficulty: str
    mode: str = "auto"


class CustomerGenerationCompareRequest(CustomerGenerationRequest):
    template_request: str
