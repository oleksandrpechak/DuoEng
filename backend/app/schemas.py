from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class GuestAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nickname: str = Field(min_length=2, max_length=20)


class GuestAuthResponse(BaseModel):
    user_id: str
    player_id: str
    nickname: str
    access_token: str
    token_type: str = "bearer"


class CreateRoomRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["classic", "challenge"] = "classic"
    target_score: int = Field(default=10, ge=1, le=100)


class JoinRoomResponse(BaseModel):
    room_code: str
    code: str
    status: str


class SubmitAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = Field(min_length=1, max_length=256)


class MoveResponse(BaseModel):
    feedback: str
    correct_answer: str
    room_code: str
    turn_number: int
    points: int
    scoring_source: str
    game_over: bool
    winner_id: Optional[str] = None


class PlayerState(BaseModel):
    user_id: str
    player_id: str
    nickname: str
    score: int
    elo: int
    is_current_turn: bool


class RoomStateResponse(BaseModel):
    room_code: str
    code: str
    status: str
    mode: str
    target_score: int
    turn_number: int
    turn_timeout_seconds: int
    players: list[PlayerState]
    current_word_ua: Optional[str] = None
    current_turn_player_id: Optional[str] = None
    turn_started_at: Optional[str] = None
    match_id: Optional[str] = None
    winner_id: Optional[str] = None
    current_turn: Optional[dict] = None
    winner: Optional[dict] = None
    last_feedback: Optional[dict] = None


class LeaderboardItem(BaseModel):
    player_id: str
    nickname: str
    elo: int
    wins: int
    losses: int
    total_games: int
    win_rate: float
    avg_response_time: float


class PlayerStatsResponse(BaseModel):
    player_id: str
    nickname: str
    elo: int
    wins: int
    losses: int
    total_games: int
    total_moves: int
    win_rate: float
    avg_response_time: float
    created_at: str


class DictionaryEntryItem(BaseModel):
    ua_word: str
    en_word: str
    part_of_speech: Optional[str] = None
    source: str


class AdminSeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_words: bool = True
    reset_stats: bool = False


class AIGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prompt: str = Field(min_length=1, max_length=4000)


class AIGenerateResponse(BaseModel):
    result: str


class WsSubmitMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["submit", "move"]
    answer: str = Field(min_length=1, max_length=256)


class WsPingMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["ping"]
