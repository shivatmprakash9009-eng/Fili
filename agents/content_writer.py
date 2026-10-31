"""Content Writer Agent — generates personalized outreach content."""

from __future__ import annotations

import json
import random
from typing import Any

from core.base_agent import BaseAgent
from core.task import Task


class ContentWriterAgent(BaseAgent):
    """Generates personalized outreach emails, follow-ups, and LinkedIn messages.

    Supports A/B testing by generating multiple content variants,
    and scores content quality.
    """

    TEMPLATES = {
        "cold_email": {
            "subject": "Quick question about {pain_point} at {company_name}",
            "body": (
                "Hi {contact_name},\n\n"
                "I noticed that {company_name} is in the {industry} space, "
                "and I wanted to reach out about {pain_point}.\n\n"
                "We've helped companies like yours {value_prop}.\n\n"
                "Would you be open to a quick 15-minute call this week?\n\n"
                "Best,\n{sender_name}"
            ),
        },
        "follow_up": {
            "subject": "Re: Following up — {company_name}",
            "body": (
                "Hi {contact_name},\n\n"
                "I wanted to follow up on my previous email. "
                "I understand you're busy, so I'll keep this short.\n\n"
                "{personalized_hook}\n\n"
                "Would a brief call work for you?\n\n"
                "Cheers,\n{sender_name}"
            ),
        },
        "linkedin_message": {
            "body": (
                "Hi {contact_name}, I came across your profile and was "
                "impressed by your work at {company_name}. "
                "I'd love to connect and share how we're helping "
                "{industry} companies {value_prop}. Open to a chat?"
            ),
        },
    }

    def __init__(self, sender_name: str = "Your Name", **kwargs: Any) -> None:
        super().__init__(name="ContentWriter", **kwargs)
        self.sender_name = sender_name

    def get_capabilities(self) -> list[str]:
        return ["generate_content", "personalize_template", "score_content"]

    async def process_task(self, task: Task) -> dict[str, Any]:
        if task.task_type == "generate_content":
            return await self.generate_content(task.payload)
        elif task.task_type == "personalize_template":
            return await self.personalize_template(task.payload)
        elif task.task_type == "score_content":
            return await self.score_content(task.payload)
        raise ValueError(f"Unknown task type: {task.task_type}")

    async def generate_content(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate personalized outreach content for leads.

        Args:
            payload: Must contain 'leads' (list) and optionally
                     'template_type', 'campaign_name', 'variants' (for A/B).
        """
        leads = payload.get("leads", [])
        # Accept leads from previous pipeline step
        if not leads:
            leads = payload.get("_previous_result", {}).get("leads", [])

        template_type = payload.get("template_type", "cold_email")
        num_variants = payload.get("variants", 1)
        campaign_name = payload.get("campaign_name", "Default Campaign")

        self.logger.info(
            f"Generating {template_type} content for {len(leads)} leads "
            f"({num_variants} variant(s))"
        )

        content_items: list[dict[str, Any]] = []

        for lead in leads:
            variants = []
            for v in range(num_variants):
                content = await self._generate_for_lead(lead, template_type, v)
                content["variant"] = chr(65 + v)  # A, B, C...
                content["quality_score"] = self._score(content)
                variants.append(content)

            best = max(variants, key=lambda x: x["quality_score"])
            content_items.append({
                "lead": lead.get("company_name", "Unknown"),
                "contact_name": lead.get("contact_name", "Decision Maker"),
                "contact_email": lead.get("contact_email", ""),
                "selected_variant": best["variant"],
                "variants": variants,
                "best_content": best,
                "lead_data": lead,
            })

        return {
            "campaign_name": campaign_name,
            "template_type": template_type,
            "content_items": content_items,
            "total_generated": len(content_items),
        }

    async def _generate_for_lead(
        self, lead: dict[str, Any], template_type: str, variant_index: int
    ) -> dict[str, Any]:
        """Generate content for a single lead."""
        pain_points = lead.get("pain_points", ["business challenges"])
        pain_point = pain_points[variant_index % len(pain_points)] if pain_points else "growth"

        value_props = [
            "reduce operational costs by 40%",
            "automate repetitive workflows and save 20+ hours per week",
            "scale their operations without increasing headcount",
            "improve customer retention by 35%",
            "accelerate their go-to-market strategy",
        ]

        placeholders = {
            "company_name": lead.get("company_name", "your company"),
            "contact_name": lead.get("contact_name", "there"),
            "industry": lead.get("industry", "technology"),
            "pain_point": pain_point,
            "value_prop": value_props[variant_index % len(value_props)],
            "sender_name": self.sender_name,
            "personalized_hook": (
                f"I noticed {lead.get('company_name', 'your company')} recently "
                f"appeared in discussions about {pain_point}."
            ),
        }

        try:
            # Try LLM-powered generation
            prompt = f"""Write a personalized {template_type.replace('_', ' ')} for:
- Company: {lead.get('company_name')}
- Contact: {lead.get('contact_name')} ({lead.get('contact_title', 'Decision Maker')})
- Industry: {lead.get('industry')}
- Pain Points: {', '.join(pain_points)}
- Tone: Professional but friendly, concise

Return JSON with keys: subject (if email), body
Keep it under 150 words."""

            response = await self.call_llm(prompt=prompt, temperature=0.9)
            parsed = self._parse_json_safe(response)
            if parsed.get("body"):
                return {"subject": parsed.get("subject", ""), "body": parsed["body"]}
        except (RuntimeError, Exception):
            pass

        # Fallback to template
        template = self.TEMPLATES.get(template_type, self.TEMPLATES["cold_email"])
        result: dict[str, Any] = {}
        if "subject" in template:
            result["subject"] = template["subject"].format(**placeholders)
        result["body"] = template["body"].format(**placeholders)
        return result

    async def personalize_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Personalize a raw template with lead data."""
        template_text = payload.get("template", "")
        lead = payload.get("lead", {})
        for key, value in lead.items():
            if isinstance(value, str):
                template_text = template_text.replace(f"{{{key}}}", value)
        return {"personalized_content": template_text}

    async def score_content(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Score content quality."""
        content = payload.get("content", {})
        return {"score": self._score(content)}

    def _score(self, content: dict[str, Any]) -> float:
        """Score content quality on a 0-10 scale."""
        body = content.get("body", "")
        score = 5.0

        # Length check (sweet spot: 80-200 words)
        word_count = len(body.split())
        if 80 <= word_count <= 200:
            score += 1.5
        elif word_count < 30:
            score -= 2.0

        # Has personalization (company/name mentioned)
        if any(c.isupper() and len(c) > 2 for c in body.split()):
            score += 1.0

        # Has call to action
        cta_phrases = ["call", "chat", "connect", "meeting", "schedule", "open to"]
        if any(phrase in body.lower() for phrase in cta_phrases):
            score += 1.0

        # Has question mark (engagement)
        if "?" in body:
            score += 0.5

        return min(round(score, 1), 10.0)

    def _parse_json_safe(self, text: str) -> dict[str, Any]:
        try:
            clean = text.strip()
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(clean[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}
