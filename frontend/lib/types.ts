export type NavItem = "overview" | "prospects" | "campaigns" | "settings";

export type EmailVerification = {
  status: string;
  mx_found: boolean;
  mailbox_verified: false;
  mx_hosts?: string[];
  note?: string;
};

export type FollowUpDraft = {
  step: number;
  day: 1 | 3 | 7;
  label: string;
  subject: string;
  body: string;
};

export type Lead = {
  company_name: string;
  website?: string;
  industry?: string;
  location?: string;
  platform?: string;
  contact_name?: string;
  contact_title?: string;
  contact_email?: string;
  phone?: string;
  email_subject?: string;
  email_body?: string;
  email_quality?: number;
  /** Sales relevance is not inferred from evidence completeness. Null means not scored. */
  relevance_score?: number | null;
  /** 0-100 provider-evidence completeness score; not a conversion probability. */
  discovery_quality_score?: number;
  relevance_score_status?: "not_scored" | string;
  quality_signals?: string[];
  field_evidence?: Record<string, { source: string; status: string }>;
  source_id?: string;
  source_url?: string;
  retrieved_at?: string;
  location_verified?: boolean;
  location_match_status?: string;
  is_live_data?: boolean;
  email_verification_status?: string;
  email_domain?: string;
  email_verification?: EmailVerification;
  phone_available?: boolean;
  whatsapp_url?: string;
  follow_up_sequence?: FollowUpDraft[];
  tech_stack?: string[];
  tech_scan_status?: string;
  source_type?: string;
  is_synthetic?: boolean;
  outreach_enabled?: boolean;
  contact_verified?: boolean;
  key_details?: string;
};

export type CampaignPayload = {
  target: string;
  location: string;
  location_scope: { country: string; country_code: string; state: string; state_code: string; city: string };
  max_leads: number;
  campaign_name: string;
  platform: "apollo" | "google_maps" | "indiamart" | "linkedin" | "web_search";
};

export type CampaignResponse = {
  success: boolean;
  error?: string;
  leads: Lead[];
  provider?: string;
  source_status?: string;
  message?: string;
  location_filter_applied?: boolean;
  diagnostics?: {
    provider?: string;
    raw_results?: number;
    normalized_results?: number;
    duplicates_removed?: number;
    rejected_by_location?: number;
    returned_results?: number;
    strict_city_filter?: boolean;
    location_verified_results?: number;
    contact_verified_results?: number;
  };
  content?: unknown[];
  report?: {
    report_title?: string;
    summary?: {
      total_leads_found?: number;
      content_pieces_generated?: number;
      emails_sent?: number;
    };
    lead_quality?: { average_score?: number };
  };
  email_activity?: { sent?: number; failed?: number; skipped?: number; dry_run?: boolean };
  email_dry_run?: boolean;
};

export type ApiStatus = {
  online: boolean;
  agents_count?: number;
  latest_campaign?: string;
  daily_schedule_enabled?: boolean;
  daily_schedule_time?: string;
  daily_schedule_timezone?: string;
  next_run?: string | null;
  last_daily_run?: { success: boolean; lead_count: number } | null;
};

export type ApiState = "checking" | "connected" | "disconnected";
