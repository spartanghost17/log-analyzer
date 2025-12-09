-- ============================================
-- PostgreSQL Database Initialization
-- Log Analysis Platform - Application Metadata
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. APPLICATION CONFIGURATION
-- ============================================
CREATE TABLE IF NOT EXISTS app_config (
    config_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    config_key VARCHAR(255) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    is_encrypted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_app_config_key ON app_config(config_key);

-- Insert default configurations
INSERT INTO app_config (config_key, config_value, description) VALUES
    ('llm.model', '"deepseek-coder:6.7b"', 'Default LLM model for analysis'),
    ('llm.temperature', '0.3', 'Temperature for LLM generation'),
    ('llm.max_tokens', '2000', 'Maximum tokens for LLM responses'),
    ('vectorization.min_level', '"WARN"', 'Minimum log level to vectorize'),
    ('vectorization.batch_size', '100', 'Batch size for embedding generation'),
    ('anomaly.sensitivity', '"medium"', 'Anomaly detection sensitivity: low, medium, high'),
    ('anomaly.z_score_threshold', '2.5', 'Z-score threshold for statistical anomalies'),
    ('notifications.email_enabled', 'true', 'Enable email notifications'),
    ('notifications.slack_enabled', 'false', 'Enable Slack notifications')
ON CONFLICT (config_key) DO NOTHING;

-- ============================================
-- 2. NIGHTLY REPORTS
-- ============================================
CREATE TABLE IF NOT EXISTS nightly_reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_date DATE NOT NULL UNIQUE,
    
    -- Time range covered
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Statistics
    total_logs_processed BIGINT,
    error_count BIGINT,
    warning_count BIGINT,
    unique_error_patterns INTEGER,
    new_error_patterns INTEGER,
    
    -- Anomaly summary
    anomalies_detected INTEGER,
    critical_issues INTEGER,
    
    -- LLM generated content
    executive_summary TEXT,
    top_issues JSONB,
    recommendations JSONB,
    
    -- Affected services
    affected_services JSONB,
    
    -- Report metadata
    generation_time_seconds REAL,
    llm_model_used VARCHAR(100),
    tokens_used INTEGER,
    
    -- Status
    status VARCHAR(50) DEFAULT 'completed',
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_nightly_reports_date ON nightly_reports(report_date DESC);
CREATE INDEX idx_nightly_reports_status ON nightly_reports(status);

-- ============================================
-- 3. ERROR PATTERN CATALOG
-- ============================================
CREATE TABLE IF NOT EXISTS error_catalog (
    catalog_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Pattern identification
    pattern_name VARCHAR(255) NOT NULL,
    error_hash VARCHAR(64) UNIQUE,
    pattern_regex TEXT,
    
    -- Classification
    category VARCHAR(100),
    severity VARCHAR(50),
    tags TEXT[],
    
    -- Description
    description TEXT,
    typical_causes TEXT[],
    common_solutions TEXT[],
    documentation_links TEXT[],
    
    -- Metadata
    is_known_issue BOOLEAN DEFAULT FALSE,
    is_expected BOOLEAN DEFAULT FALSE,
    auto_created BOOLEAN DEFAULT FALSE,
    
    -- Relationships
    related_patterns UUID[],
    
    -- Analysis
    avg_resolution_time INTERVAL,
    last_occurrence TIMESTAMP WITH TIME ZONE,
    total_occurrences BIGINT DEFAULT 0,
    
    -- Audit
    created_by VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_error_catalog_category ON error_catalog(category);
CREATE INDEX idx_error_catalog_severity ON error_catalog(severity);
CREATE INDEX idx_error_catalog_hash ON error_catalog(error_hash);

-- ============================================
-- 4. ANOMALY ALERTS
-- ============================================
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Anomaly identification
    anomaly_type VARCHAR(50) NOT NULL,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Context
    service VARCHAR(255),
    environment VARCHAR(50),
    time_window INTERVAL,
    
    -- Details
    description TEXT,
    metrics JSONB,
    affected_log_ids UUID[],
    sample_logs JSONB,
    
    -- ClickHouse reference
    clickhouse_query TEXT,
    
    -- Qdrant reference
    qdrant_point_ids TEXT[],
    
    -- Severity assessment
    severity VARCHAR(50),
    confidence_score REAL,
    
    -- LLM analysis
    llm_analysis TEXT,
    suggested_actions JSONB,
    
    -- Alert status
    status VARCHAR(50) DEFAULT 'new',
    acknowledged_by VARCHAR(255),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    resolved_at TIMESTAMP WITH TIME ZONE,
    
    -- Notification tracking
    notifications_sent JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_anomaly_alerts_detected_at ON anomaly_alerts(detected_at DESC);
CREATE INDEX idx_anomaly_alerts_service ON anomaly_alerts(service);
CREATE INDEX idx_anomaly_alerts_status ON anomaly_alerts(status);
CREATE INDEX idx_anomaly_alerts_severity ON anomaly_alerts(severity);

-- ============================================
-- 5. SERVICE REGISTRY
-- ============================================
CREATE TABLE IF NOT EXISTS services (
    service_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(255) UNIQUE NOT NULL,
    
    -- Metadata
    description TEXT,
    team VARCHAR(255),
    owner_email VARCHAR(255),
    repository_url TEXT,
    
    -- Monitoring configuration
    enabled BOOLEAN DEFAULT TRUE,
    log_retention_days INTEGER DEFAULT 90,
    vectorize_logs BOOLEAN DEFAULT TRUE,
    vectorize_levels TEXT[] DEFAULT ARRAY['WARN', 'ERROR', 'FATAL'],
    
    -- Thresholds
    error_rate_threshold REAL,
    anomaly_sensitivity VARCHAR(50) DEFAULT 'medium',
    
    -- Alert configuration
    alert_email TEXT[],
    alert_slack_channel VARCHAR(255),
    alert_on_new_patterns BOOLEAN DEFAULT TRUE,
    
    -- Tags
    tags TEXT[],
    environment_tags JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_services_enabled ON services(enabled);
CREATE INDEX idx_services_name ON services(service_name);

-- Insert sample services
INSERT INTO services (service_name, description, team, vectorize_logs, tags) VALUES
    ('api-gateway', 'Main API gateway service', 'Platform', true, ARRAY['critical', 'external-facing']),
    ('user-service', 'User management service', 'Identity', true, ARRAY['critical', 'data-sensitive']),
    ('payment-service', 'Payment processing service', 'Payments', true, ARRAY['critical', 'pci-compliant']),
    ('notification-service', 'Notification delivery service', 'Communications', true, ARRAY['high-volume']),
    ('auth-service', 'Authentication service', 'Identity', true, ARRAY['critical', 'security'])
ON CONFLICT (service_name) DO NOTHING;

-- ============================================
-- 6. USER PREFERENCES
-- ============================================
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255),
    
    -- Dashboard preferences
    default_time_range VARCHAR(50) DEFAULT '24h',
    default_services TEXT[],
    default_environments TEXT[],
    
    -- Saved queries
    saved_queries JSONB,
    
    -- Notification preferences
    email_notifications BOOLEAN DEFAULT TRUE,
    slack_notifications BOOLEAN DEFAULT FALSE,
    notification_frequency VARCHAR(50) DEFAULT 'immediate',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- 7. ANALYSIS JOBS (Track LLM Analysis Tasks)
-- ============================================
CREATE TABLE IF NOT EXISTS analysis_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type VARCHAR(50) NOT NULL,
    
    -- Job parameters
    parameters JSONB,
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    result JSONB,
    error_message TEXT,
    
    -- Resource usage
    processing_time_seconds REAL,
    tokens_used INTEGER,
    model_used VARCHAR(100),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX idx_analysis_jobs_type ON analysis_jobs(job_type);
CREATE INDEX idx_analysis_jobs_created ON analysis_jobs(created_at DESC);

-- ============================================
-- 8. TRIGGERS FOR UPDATED_AT
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers to tables
CREATE TRIGGER update_app_config_updated_at BEFORE UPDATE ON app_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_error_catalog_updated_at BEFORE UPDATE ON error_catalog
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_anomaly_alerts_updated_at BEFORE UPDATE ON anomaly_alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_services_updated_at BEFORE UPDATE ON services
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 9. HELPER VIEWS
-- ============================================

-- View: Recent critical alerts
CREATE OR REPLACE VIEW recent_critical_alerts AS
SELECT 
    alert_id,
    anomaly_type,
    service,
    severity,
    description,
    detected_at,
    status
FROM anomaly_alerts
WHERE severity IN ('high', 'critical')
    AND detected_at >= NOW() - INTERVAL '7 days'
ORDER BY detected_at DESC;

-- View: Service health summary
CREATE OR REPLACE VIEW service_health_summary AS
SELECT
    s.service_name,
    s.enabled,
    COUNT(aa.alert_id) as active_alerts,
    MAX(aa.detected_at) as last_alert_time
FROM services s
LEFT JOIN anomaly_alerts aa ON s.service_name = aa.service AND aa.status = 'new'
GROUP BY s.service_id, s.service_name, s.enabled;

-- ============================================
-- INITIALIZATION COMPLETE
-- ============================================
SELECT 'PostgreSQL initialization completed successfully!' as status;