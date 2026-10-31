"""Response Analyzer Agent — analyzes email replies using LLM."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from core.base_agent import BaseAgent
from core.task import Task


class ResponseCategory(str, Enum):
    """Categories for email response classification."""
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    MEETING_REQUEST = "meeting_request"
    OUT_OF_OFFICE = "out_of_office"
    BOUNCE = "bounce"
    UNSUBSCRIBE = "unsubscribe"
    NEEDS_INFO = "needs_more_info"
    UNKNOWN = "unknown"


class ResponseAnalyzerAgent(BaseAgent):
    """Analyzes email responses using LLM for classification, sentiment,
    and action-item extraction."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="ResponseAnalyzer", **kwargs)

    def get_capabilities(self) -> list[str]:
        return ["analyze_response", "categorize_responses", "extract_action_items"]

    async def process_task(self, task: Task) -> dict[str, Any]:
        if task.task_type == "analyze_response":
            return await self.analyze_response(task.payload)
        elif task.task_type == "categorize_responses":
            return await self.categorize_responses(task.payload)
        elif task.task_type == "extract_action_items":
            return await self.extract_action_items(task.payload)
        raise ValueError(f"Unknown task type: {task.task_type}")

    async def analyze_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Fully analyze a single email response.

        Args:
            payload: Must contain 'response_text', optionally 'lead_info'.
        """
        response_text = payload.get("response_text", "")
        lead_info = payload.get("lead_info", {})

        category = await self._categorize(response_text)
        sentiment = self._analyze_sentiment(response_text)
        action_items = await self._extract_actions(response_text, category)
        next_action = self._suggest_next_action(category, sentiment)

        return {
            "category": category.value,
            "sentiment": sentiment,
            "action_items": action_items,
            "next_action": next_action,
            "lead": lead_info.get("company_name", "Unknown"),
            "summary": self._generate_summary(category, sentiment, response_text),
        }

    async def categorize_responses(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Categorize multiple responses.

        Args:
            payload: Must contain 'responses' — list of dicts with
                     'response_text' and optional 'lead_info'.
        """
        responses = payload.get("responses", [])
        results: list[dict[str, Any]] = []
        category_counts: dict[str, int] = {}

        for resp in responses:
            text = resp.get("response_text", "")
            category = await self._categorize(text)
            category_counts[category.value] = category_counts.get(category.value, 0) + 1
            results.append({
                "lead": resp.get("lead_info", {}).get("company_name", "Unknown"),
                "category": category.value,
                "sentiment": self._analyze_sentiment(text),
            })

        return {
            "results": results,
            "category_summary": category_counts,
            "total_analyzed": len(results),
        }

    async def extract_action_items(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract action items from a response."""
        text = payload.get("response_text", "")
        category = await self._categorize(text)
        actions = await self._extract_actions(text, category)
        return {"action_items": actions}

    # ── Private Helpers ───────────────────────────────────────────

    async def _categorize(self, text: str) -> ResponseCategory:
        """Categorize a response text."""
        text_lower = text.lower()

        # Rule-based fast checks
        if any(w in text_lower for w in ["unsubscribe", "remove me", "stop emailing", "opt out"]):
            return ResponseCategory.UNSUBSCRIBE
        if any(w in text_lower for w in ["out of office", "on vacation", "ooo", "auto-reply", "away from my desk", "annual leave"]):
            return ResponseCategory.OUT_OF_OFFICE
        if any(w in text_lower for w in ["delivery failed", "undeliverable", "bounced", "mailer-daemon"]):
            return ResponseCategory.BOUNCE
        if any(w in text_lower for w in ["schedule", "meeting", "calendar", "calendly", "book a call", "book a", "call on", "minute call", "quick call", "zoom", "let's meet"]):
            return ResponseCategory.MEETING_REQUEST
        if any(w in text_lower for w in ["not interested", "no thanks", "not a fit", "pass on this", "no thank you", "not looking"]):
            return ResponseCategory.NOT_INTERESTED
        if any(w in text_lower for w in ["interested", "interesting", "tell me more", "sounds good", "let's talk", "love to", "keen to", "curious"]):
            return ResponseCategory.INTERESTED
        if any(w in text_lower for w in ["more info", "more information", "details", "pricing", "cost", "how does it work", "case study", "deck", "sheet"]):
            return ResponseCategory.NEEDS_INFO

        # Try LLM for ambiguous cases
        try:
            prompt = f"""Categorize this email response into one of these categories:
- interested
- not_interested
- meeting_request
- out_of_office
- bounce
- unsubscribe
- needs_more_info
- unknown

Email response:
\"\"\"
{text[:500]}
\"\"\"

Return ONLY the category name, nothing else."""

            result = await self.call_llm(prompt=prompt, temperature=0.1, max_tokens=50)
            cat = result.strip().lower().replace(" ", "_")
            try:
                return ResponseCategory(cat)
            except ValueError:
                pass
        except (RuntimeError, Exception):
            pass

        return ResponseCategory.UNKNOWN

    def _analyze_sentiment(self, text: str) -> dict[str, Any]:
        """Simple rule-based sentiment analysis."""
        text_lower = text.lower()

        positive_words = [
            "great", "interested", "love", "perfect", "excellent",
            "excited", "happy", "sounds good", "wonderful", "awesome",
        ]
        negative_words = [
            "not interested", "no", "stop", "unsubscribe", "spam",
            "annoying", "terrible", "worst", "disappointed", "don't",
        ]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count > neg_count:
            sentiment = "positive"
            confidence = min(0.5 + pos_count * 0.15, 0.95)
        elif neg_count > pos_count:
            sentiment = "negative"
            confidence = min(0.5 + neg_count * 0.15, 0.95)
        else:
            sentiment = "neutral"
            confidence = 0.5

        return {
            "label": sentiment,
            "confidence": round(confidence, 2),
            "positive_signals": pos_count,
            "negative_signals": neg_count,
        }

    async def _extract_actions(
        self, text: str, category: ResponseCategory
    ) -> list[str]:
        """Extract action items based on category and content."""
        actions: list[str] = []

        if category == ResponseCategory.INTERESTED:
            actions.append("Send detailed proposal/case study")
            actions.append("Schedule discovery call")
        elif category == ResponseCategory.MEETING_REQUEST:
            actions.append("Send calendar link for meeting")
            actions.append("Prepare meeting agenda")
        elif category == ResponseCategory.NEEDS_INFO:
            actions.append("Send product details/pricing sheet")
            actions.append("Follow up in 2-3 days")
        elif category == ResponseCategory.NOT_INTERESTED:
            actions.append("Mark as not interested")
            actions.append("Schedule re-engagement in 3-6 months")
        elif category == ResponseCategory.UNSUBSCRIBE:
            actions.append("Remove from mailing list immediately")
        elif category == ResponseCategory.OUT_OF_OFFICE:
            actions.append("Schedule follow-up after return date")
        elif category == ResponseCategory.BOUNCE:
            actions.append("Verify email address")
            actions.append("Find alternative contact")

        return actions

    def _suggest_next_action(
        self, category: ResponseCategory, sentiment: dict[str, Any]
    ) -> str:
        """Suggest the best next action."""
        action_map = {
            ResponseCategory.INTERESTED: "Schedule a call ASAP — hot lead!",
            ResponseCategory.MEETING_REQUEST: "Send calendar link immediately",
            ResponseCategory.NEEDS_INFO: "Send detailed info packet and follow up in 3 days",
            ResponseCategory.NOT_INTERESTED: "Archive and revisit in 3-6 months",
            ResponseCategory.UNSUBSCRIBE: "Remove from all lists — compliance required",
            ResponseCategory.OUT_OF_OFFICE: "Set reminder to follow up after return",
            ResponseCategory.BOUNCE: "Find new email for this contact",
            ResponseCategory.UNKNOWN: "Manually review this response",
        }
        return action_map.get(category, "Review manually")

    def _generate_summary(
        self, category: ResponseCategory, sentiment: dict[str, Any], text: str
    ) -> str:
        """Generate a brief summary of the analysis."""
        return (
            f"Response categorized as '{category.value}' with "
            f"{sentiment['label']} sentiment "
            f"(confidence: {sentiment['confidence']:.0%}). "
            f"Preview: \"{text[:80]}...\""
            if len(text) > 80
            else f"Response categorized as '{category.value}' with "
                 f"{sentiment['label']} sentiment. "
                 f"Content: \"{text}\""
        )
