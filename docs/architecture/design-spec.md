# QE Copilot — AI-Powered Test Generation and Defect Triage Platform

## Engineering Design and Project Implementation Specification

**Document type:** System Design Document
**Project category:** AI Tooling, Quality Engineering Platform, Backend Engineering
**Primary users:** Quality Engineers, Software Engineers, QE Leads, Platform Engineers
**Primary objective:** Accelerate test creation, CI failure analysis, defect triage, and quality-engineering workflows using production-grade AI-powered tooling.

---

# 1. Executive Summary

QE Copilot is an internal engineering platform that integrates artificial intelligence into software quality-engineering workflows.

The system will:

* Generate structured and executable test cases from requirements, user stories, API specifications, and technical documentation.
* Ingest CI/CD pipeline results and automatically analyse failed test runs.
* Summarise large logs into concise, actionable failure reports.
* Identify likely root causes and probable service owners.
* Find similar historical defects using embeddings and vector retrieval.
* Recommend defect severity, category, ownership, and remediation steps.
* Provide evidence-backed recommendations using Retrieval-Augmented Generation.
* Collect human feedback to measure and improve AI output quality.
* Expose its functionality through a complete frontend dashboard, REST APIs, command-line interface, and CI/CD integrations.

The project will be built as a production-style internal platform rather than a simple LLM wrapper.

The backend will use a modular-monolith architecture with separately deployable asynchronous workers. This architecture provides clear domain separation, maintainability, scalability, and deployment simplicity without introducing unnecessary distributed-system complexity.

---

# 2. Problem Statement

Quality engineering teams spend significant time on repetitive and manually intensive activities:

* Converting requirements into test cases.
* Reviewing thousands of lines of CI logs.
* Identifying whether a failure is new or already known.
* Determining which team owns a failed component.
* Searching historical defects and runbooks.
* Assigning severity and category to incidents.
* Writing defect descriptions and investigation summaries.
* Repeating diagnostic work already completed by another engineer.
* Maintaining consistency across manually written tests.

These workflows create several operational problems:

1. Slow failure-triage cycles.
2. Duplicated defects and investigations.
3. Inconsistent test coverage.
4. Delayed feedback to engineering teams.
5. Poor visibility into common failure patterns.
6. Dependence on individual engineer experience.
7. Low reuse of historical incident knowledge.
8. High cognitive load during CI failure investigation.

QE Copilot will address these problems by providing structured AI assistance while keeping humans responsible for final decisions.

---

# 3. Project Vision

The long-term vision is to create an intelligent quality-engineering platform that acts as a central operational layer between:

* Product requirements
* Source-code repositories
* Test automation frameworks
* CI/CD systems
* Defect-management systems
* Engineering documentation
* Historical incidents
* Quality-engineering teams

The system should not behave like a generic chatbot.

It should provide workflow-specific capabilities that produce structured, traceable, measurable, and reviewable engineering outputs.

---

# 4. Project Goals

## 4.1 Primary Goals

The platform must:

1. Generate useful test scenarios from engineering requirements.
2. Generate executable test-code skeletons.
3. Analyse failed CI/CD executions.
4. Summarise noisy test and application logs.
5. Classify failures into predefined categories.
6. Retrieve similar historical incidents.
7. recommend likely root causes and owning teams.
8. Provide evidence supporting each recommendation.
9. Expose all major workflows through a frontend dashboard.
10. Provide APIs and a CLI for automation.
11. Integrate with GitHub Actions.
12. Track AI model usage, latency, quality, and cost.
13. Support human review and feedback.
14. Protect credentials, tokens, personal data, and internal information.
15. Provide comprehensive automated test coverage.

## 4.2 Secondary Goals

The platform should:

* Support multiple repositories and projects.
* Support multiple LLM and embedding providers.
* Allow prompt versioning.
* Provide configurable AI confidence thresholds.
* Support scheduled knowledge-base ingestion.
* Allow users to compare AI-generated and human-approved results.
* Offer Kubernetes-compatible deployment.
* Support future integrations with Jira, Jenkins, GitLab, and Slack.

---

# 5. Non-Goals

The initial system will not:

* Automatically merge generated tests into production branches.
* Automatically close defects without human review.
* Replace quality engineers.
* Execute unrestricted AI-generated code.
* Automatically modify production infrastructure.
* Train a foundation model from scratch.
* Support unrestricted autonomous agents.
* Perform production incident remediation.
* Support every programming language and testing framework during the initial release.
* Become a full replacement for Jira, GitHub, or CI platforms.

These exclusions reduce risk and keep the first release achievable.

---

# 6. Target Users

## 6.1 Quality Engineer

Primary needs:

* Generate test cases.
* Analyse failed tests.
* Find similar defects.
* Create structured defect reports.
* Review AI suggestions.
* Provide feedback on recommendations.

## 6.2 Software Engineer

Primary needs:

* Understand why a CI build failed.
* Identify the likely failing service.
* View relevant logs and evidence.
* Find previous incidents with similar symptoms.
* Receive recommended diagnostic actions.

## 6.3 QE Lead

Primary needs:

* Monitor test-generation adoption.
* View common failure categories.
* Measure triage efficiency.
* Review model accuracy.
* Analyse team feedback.
* Manage quality thresholds.

## 6.4 Platform Engineer

Primary needs:

* Configure CI integrations.
* Manage repositories and projects.
* Monitor worker health and queues.
* Configure authentication and secrets.
* Review platform performance and reliability.

## 6.5 Administrator

Primary needs:

* Manage users and permissions.
* Configure AI providers.
* Manage prompt versions.
* Control retention policies.
* Review audit logs.
* Configure integrations.

---

# 7. Core Product Capabilities

## 7.1 AI-Assisted Test Generation

Users will generate tests from:

* User stories
* Acceptance criteria
* Product requirements
* OpenAPI specifications
* Existing test suites
* Technical documentation
* Bug descriptions
* Service contracts

The system will generate:

* Positive test scenarios
* Negative test scenarios
* Boundary cases
* Edge cases
* Security-related test scenarios
* API contract tests
* Regression tests
* Data-validation cases
* Failure-recovery scenarios
* Test preconditions
* Test steps
* Expected results
* Test priority
* Test tags
* Automation feasibility
* Executable test skeletons

Initially supported test frameworks:

* Pytest
* Playwright
* REST API tests using Python
* Generic structured manual-test format

Generated tests must pass through:

1. Schema validation
2. Duplicate detection
3. Static analysis
4. Syntax validation
5. Optional sandbox execution
6. Human review

---

## 7.2 CI/CD Failure Ingestion

The platform will integrate with GitHub Actions using webhooks.

It will ingest:

* Workflow metadata
* Repository information
* Branch and commit
* Pull-request information
* Workflow name
* Job and step details
* Test reports
* Standard output
* Standard error
* Exit codes
* Build artifacts
* Timing information

The system will preserve the original evidence while generating a cleaned and normalised representation for AI processing.

---

## 7.3 Log Summarisation

The log-analysis pipeline will:

1. Detect log format.
2. Remove repeated lines.
3. Group stack traces.
4. Identify timestamps and services.
5. Detect error messages.
6. Extract exception types.
7. Extract HTTP status codes.
8. Detect timeouts and retry patterns.
9. Detect dependency failures.
10. Remove secrets and sensitive data.
11. Generate a deterministic failure signature.
12. Retrieve related incidents.
13. Produce a concise failure summary.

Output structure:

* Failure category
* Failure summary
* First relevant error
* Probable cause
* Affected service
* Probable owner
* Related incidents
* Recommended next action
* Supporting evidence
* Confidence score

---

## 7.4 Defect Triage

The triage module will recommend:

* Defect title
* Defect description
* Severity
* Priority
* Failure category
* Component
* Probable owning team
* Root-cause hypothesis
* Reproduction information
* Similar historical defects
* Recommended diagnostic steps
* Evidence references
* Confidence level

A user must approve or edit the result before it is exported to an external defect-management platform.

---

## 7.5 Similar-Defect Retrieval

The platform will use embeddings and metadata filters to search:

* Historical defects
* Previous CI failures
* Runbooks
* Post-incident reviews
* Service documentation
* Troubleshooting guides
* Test reports

Retrieval will use both:

* Semantic vector similarity
* Structured metadata filters

Example filters:

* Repository
* Service
* Environment
* Failure category
* Date range
* Team
* Test suite
* Severity
* Error code

---

## 7.6 Knowledge-Base Management

The system will allow authorised users to ingest:

* Markdown
* Plain text
* PDF
* JSON
* CSV
* OpenAPI files
* Runbooks
* Defect exports
* Test-case exports

Knowledge ingestion will include:

1. File validation
2. Malware-safe handling
3. Content extraction
4. Data normalisation
5. Sensitive-data redaction
6. Document chunking
7. Metadata extraction
8. Embedding generation
9. Vector indexing
10. Version management

---

## 7.7 Human Feedback

Users will be able to rate AI outputs as:

* Correct
* Mostly correct
* Partially correct
* Incorrect
* Helpful
* Not helpful

Users may also correct:

* Failure category
* Severity
* Owning team
* Root cause
* Suggested action
* Generated test content

Feedback will be stored as structured evaluation data.

The system will not immediately retrain models from user feedback. Feedback will first be reviewed and used for evaluation, prompt improvement, and future dataset development.

---

## 7.8 Command-Line Interface

The CLI will support developer workflows without requiring the dashboard.

Example commands:

```bash
qe-copilot login
qe-copilot generate-tests requirements.md
qe-copilot analyse-log build.log
qe-copilot triage --build-id build_1042
qe-copilot similar-defects --failure-id fail_201
qe-copilot upload-knowledge runbook.md
qe-copilot job-status job_4821
```

The CLI will call the same public backend APIs used by the frontend.

No business logic will be duplicated inside the CLI.

---

# 8. System Design Principles

## 8.1 Backend-First Design

The dashboard will consume documented APIs. Core functionality must not exist only in frontend code.

## 8.2 Human-in-the-Loop

AI recommendations are suggestions. Humans retain authority over:

* Defect creation
* Severity assignment
* Test approval
* Code changes
* External-system updates

## 8.3 Evidence-Grounded AI

Every material AI recommendation should include supporting evidence such as:

* Relevant log lines
* Similar incidents
* Runbook sections
* Test-result metadata
* Service documentation

## 8.4 Asynchronous Processing

Long-running AI, ingestion, and analysis workloads will be processed through background jobs.

## 8.5 Provider Abstraction

The application will not directly couple domain logic to a single LLM provider.

## 8.6 Security by Default

Logs and documents will be treated as untrusted and potentially sensitive.

## 8.7 Measurable Quality

The platform must track whether its outputs are:

* Accurate
* Accepted
* Useful
* Fast
* Cost-effective
* Evidence-backed

## 8.8 Controlled Complexity

The first release will use a modular monolith instead of premature microservices.

This provides:

* Easier local development
* Simpler transactions
* Easier debugging
* Lower deployment overhead
* Clear module boundaries
* Future service-extraction capability

---

# 9. High-Level Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       External Systems                       │
│                                                             │
│ GitHub Actions   GitHub Repositories   Future Jira/Jenkins  │
└──────────────┬───────────────────────────────┬──────────────┘
               │ Webhooks                      │ API
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      API Application                         │
│                    Python + FastAPI                          │
│                                                             │
│ Authentication        Integration Management                │
│ Test Generation       CI Failure Ingestion                  │
│ Log Analysis          Defect Triage                         │
│ Knowledge Management  Similarity Search                     │
│ Feedback              Reporting                             │
│ Administration        Audit                                 │
└──────────────┬──────────────────────┬───────────────────────┘
               │                      │
               │ Job creation         │ Synchronous queries
               ▼                      ▼
┌──────────────────────┐     ┌───────────────────────────────┐
│ Async Worker Service │     │ PostgreSQL + pgvector         │
│                      │     │                               │
│ AI generation        │     │ Application records           │
│ Embedding generation │     │ Metadata                      │
│ Document ingestion   │     │ Vector embeddings             │
│ Log processing       │     │ Audit history                 │
│ Evaluation           │     │ Prompt versions               │
└──────────┬───────────┘     └───────────────────────────────┘
           │
           ▼
┌──────────────────────┐
│ Redis                │
│                      │
│ Task queue           │
│ Distributed locks    │
│ Rate-limit state     │
│ Short-lived cache    │
└──────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     AI Provider Layer                        │
│                                                             │
│ LLM Provider   Embedding Provider   Optional Local Models    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   Frontend Dashboard                         │
│                                                             │
│ Next.js + TypeScript                                        │
│ CI failures, test generation, triage, knowledge, analytics  │
└─────────────────────────────────────────────────────────────┘
```

---

# 10. Recommended Technology Stack

## 10.1 Frontend

* Next.js
* TypeScript
* React
* Component library such as shadcn/ui
* Tailwind CSS
* TanStack Query for server-state management
* React Hook Form
* Zod validation
* Recharts or equivalent visualisation library
* Server-sent events or WebSockets for job updates
* Playwright for end-to-end tests

## 10.2 Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy
* Alembic
* PostgreSQL
* pgvector
* Redis
* Celery or Dramatiq
* Pytest
* Ruff
* MyPy
* OpenTelemetry

## 10.3 AI and Retrieval

* Provider-neutral LLM interface
* Provider-neutral embedding interface
* Structured JSON generation
* Prompt registry
* Retrieval pipeline
* Metadata filtering
* Optional reranking
* Evaluation datasets
* Token and cost tracking

## 10.4 Infrastructure

* Docker
* Docker Compose
* Kubernetes manifests
* Helm chart
* GitHub Actions
* AWS reference deployment
* Terraform for infrastructure
* S3-compatible object storage
* Secrets Manager or equivalent
* Managed PostgreSQL
* Managed Redis

---

# 11. Frontend Dashboard Specification

The frontend will show the complete platform workflow and provide operational visibility into all major backend processes.

## 11.1 Global Layout

The application shell will contain:

### Left Navigation

* Overview
* CI Failures
* Test Generator
* Defect Triage
* Knowledge Base
* Evaluations
* Analytics
* Integrations
* System Health
* Administration

### Top Navigation

* Project selector
* Repository selector
* Environment selector
* Global search
* Notifications
* Current user
* Help and documentation

### Global Status Indicators

* API health
* Worker health
* Queue depth
* AI-provider status
* Last ingestion time
* Integration status

---

## 11.2 Overview Dashboard

The Overview page will display:

### Summary Cards

* Failed builds in the last 24 hours
* Untriaged failures
* AI-triaged failures
* Test cases generated
* Average triage time
* AI recommendation acceptance rate
* Active background jobs
* Knowledge-base document count

### Visualisations

* Failures by category
* Failures by service
* Failures over time
* Most unstable test suites
* Most common root-cause hypotheses
* AI confidence distribution
* Generated tests by type
* Triage time before and after AI assistance

### Activity Feed

* New failed build
* Completed log analysis
* Human-approved triage
* Knowledge document indexed
* Prompt version changed
* Integration error
* Feedback submitted

---

## 11.3 CI Failures Page

The CI Failures page will provide:

* Search
* Filtering
* Sorting
* Pagination
* Saved filters
* Bulk selection

Filters:

* Repository
* Branch
* Commit
* Pull request
* Workflow
* Test suite
* Service
* Failure category
* Triage status
* Severity
* Date range
* Confidence range
* Assigned team

Table columns:

* Build number
* Repository
* Branch
* Commit
* Failed test count
* Primary category
* Probable owner
* Severity
* Confidence
* Status
* Created time
* Analysis duration

Actions:

* Open failure
* Start analysis
* Re-run analysis
* Assign owner
* Mark as known issue
* Link defect
* Export triage summary

---

## 11.4 Failure Detail Page

The Failure Detail page is a central project feature.

It will contain the following sections.

### Build Context

* Repository
* Workflow
* Job
* Branch
* Commit
* Pull request
* Author
* Start and end time
* Environment
* Test framework
* Build URL

### AI Summary

* Failure summary
* Probable root cause
* Failure category
* Recommended severity
* Probable owner
* Recommended next action
* Confidence score

### Evidence Panel

* Relevant log lines
* Stack traces
* Error codes
* Failing test names
* Failed service calls
* Referenced runbook sections
* Related historical incidents

Every recommendation must link to its evidence.

### Raw Logs

* Searchable log viewer
* Line numbers
* Syntax highlighting
* Collapsible stack traces
* Download option
* Sensitive-data redaction indicators
* Original versus redacted view based on permission

### Similar Incidents

Each related incident will show:

* Incident ID
* Title
* Similarity score
* Resolution
* Root cause
* Owning team
* Date
* Link to complete incident

### Human Review

Users can:

* Accept analysis
* Edit category
* Change severity
* Change owning team
* Correct root cause
* Add investigation notes
* Mark analysis as inaccurate
* Submit feedback

### Processing History

* Analysis attempts
* Prompt version
* Model used
* Retrieval results
* Processing duration
* Token usage
* Errors and retries

---

## 11.5 Test Generator Page

The Test Generator page will include:

### Input Sources

* Manual requirement entry
* User-story text
* Acceptance criteria
* OpenAPI upload
* Existing-test upload
* Documentation selection
* Repository context

### Test Configuration

* Test type
* Framework
* Target service
* Number of tests
* Include positive cases
* Include negative cases
* Include boundary cases
* Include security cases
* Include accessibility cases
* Desired test priority
* Maximum generation cost

### Generated Results

Each test will display:

* Title
* Objective
* Preconditions
* Test data
* Steps
* Expected result
* Priority
* Tags
* Source requirement
* Generated code
* Validation status
* Duplicate score
* Execution status

### User Actions

* Edit test
* Approve test
* Reject test
* Regenerate one test
* Regenerate all tests
* Download tests
* Copy generated code
* Export as JSON
* Create pull-request draft
* Save as test template

---

## 11.6 Defect Triage Page

Users will be able to create a triage case from:

* A CI failure
* Uploaded logs
* Manual defect description
* Existing defect
* API request

The result page will display:

* Suggested defect title
* Suggested description
* Severity
* Priority
* Component
* Owner
* Root-cause hypothesis
* Reproduction details
* Similar defects
* Recommended investigation
* Confidence
* Evidence

The system will show each field separately so users can accept or modify individual recommendations.

---

## 11.7 Knowledge Base Page

Capabilities:

* Upload document
* View ingestion status
* View document metadata
* Search indexed content
* Preview extracted text
* View chunk count
* View embedding status
* Re-index document
* Disable document
* Delete document
* Review document versions
* Configure metadata and access scope

Document states:

* Uploaded
* Validating
* Extracting
* Redacting
* Chunking
* Embedding
* Indexed
* Failed
* Disabled

---

## 11.8 Evaluations Page

The Evaluations page will support controlled AI evaluation.

It will show:

* Evaluation dataset
* Prompt version
* Model
* Embedding model
* Accuracy
* Precision
* Recall
* Mean reciprocal rank
* Human acceptance rate
* Hallucination rate
* Average latency
* Average cost
* Comparison with previous version

Users will be able to compare two prompt or model configurations before promoting a change.

---

## 11.9 Analytics Page

Metrics:

* Mean time to triage
* Median time to triage
* Failure recurrence rate
* Duplicate defect rate
* AI acceptance rate
* Correct ownership rate
* Correct classification rate
* Test-generation approval rate
* Generated-test execution success
* Cost per analysis
* Cost per approved output
* Model latency
* Retrieval quality
* Top failing services
* Top unstable tests

---

## 11.10 Integration Management Page

Initial integration:

* GitHub

Future integrations:

* Jira
* Jenkins
* GitLab
* Slack
* Microsoft Teams

GitHub configuration will include:

* Organisation
* Repository
* Webhook status
* Webhook secret
* Events enabled
* Last delivery
* Failed deliveries
* Test-report locations
* Allowed branches

---

## 11.11 System Health Page

The page will display:

* API uptime
* API response latency
* Worker status
* Queue depth
* Failed jobs
* Redis connectivity
* PostgreSQL connectivity
* AI-provider status
* Object-storage status
* Recent application errors
* Deployment version
* Database migration version

---

# 12. Backend Architecture

## 12.1 Architecture Style

The backend will begin as a modular monolith containing strongly separated domain modules.

Separately deployed processes:

1. API service
2. Background-worker service
3. Scheduler service
4. Frontend application

The API and worker will use the same domain packages but will run as independent containers.

This permits horizontal scaling without introducing multiple independently versioned services.

---

## 12.2 Backend Modules

```text
Authentication
User Management
Organisation Management
Project Management
Repository Integration
CI Ingestion
Build Management
Test Result Management
Log Processing
Test Generation
Defect Triage
Knowledge Management
Retrieval
AI Provider Gateway
Prompt Management
Feedback
Evaluation
Reporting
Notifications
Audit
Administration
```

Each module will own:

* Domain models
* Service layer
* Repository interfaces
* Validation
* Events
* API schemas
* Tests

Modules must not directly modify another module's database records through uncontrolled queries.

Cross-module actions will occur through:

* Defined service interfaces
* Domain events
* Shared identifiers

---

# 13. Backend Request Lifecycle

## 13.1 Synchronous Request

Used for:

* Read operations
* Searches
* User configuration
* Lightweight validation
* Health checks

```text
Client
  ↓
API router
  ↓
Authentication
  ↓
Request validation
  ↓
Application service
  ↓
Repository/data access
  ↓
Response mapping
  ↓
Client
```

## 13.2 Asynchronous Request

Used for:

* Test generation
* Log analysis
* Document ingestion
* Embedding creation
* Bulk evaluations
* Large report generation

```text
Client
  ↓
API validates request
  ↓
Database job created
  ↓
Queue message published
  ↓
API returns job ID
  ↓
Worker claims job
  ↓
Worker processes job
  ↓
Worker stores result
  ↓
Frontend receives status update
```

---

# 14. Background Job Model

Job states:

```text
PENDING
QUEUED
RUNNING
WAITING_FOR_PROVIDER
VALIDATING
COMPLETED
PARTIALLY_COMPLETED
FAILED
CANCELLED
TIMED_OUT
```

Every job will include:

* Job ID
* Job type
* User
* Project
* Status
* Progress percentage
* Attempt count
* Maximum attempts
* Created timestamp
* Started timestamp
* Completed timestamp
* Input reference
* Output reference
* Error code
* Redacted error message
* Trace ID
* Idempotency key

Worker requirements:

* Retry with exponential backoff
* Maximum retry count
* Dead-letter handling
* Per-job timeout
* Distributed lock where required
* Idempotent task processing
* Graceful shutdown
* Visibility timeout
* Metrics
* Trace propagation

---

# 15. Database Design

## 15.1 Identity and Access Tables

### organisations

* id
* name
* slug
* status
* created_at
* updated_at

### users

* id
* organisation_id
* external_identity_id
* email
* display_name
* status
* created_at
* updated_at
* last_login_at

### roles

* id
* name
* description

### user_roles

* user_id
* role_id
* project_id

---

## 15.2 Project and Integration Tables

### projects

* id
* organisation_id
* name
* description
* status
* created_at
* updated_at

### repositories

* id
* project_id
* provider
* external_repository_id
* owner
* name
* default_branch
* webhook_status
* created_at
* updated_at

### integration_credentials

* id
* organisation_id
* integration_type
* encrypted_secret_reference
* status
* created_at
* rotated_at

No plaintext access tokens will be stored directly in the database.

---

## 15.3 CI and Test Tables

### pipeline_runs

* id
* repository_id
* external_run_id
* workflow_name
* branch
* commit_sha
* pull_request_number
* actor
* status
* conclusion
* started_at
* completed_at
* external_url

### pipeline_jobs

* id
* pipeline_run_id
* external_job_id
* name
* status
* conclusion
* started_at
* completed_at

### test_runs

* id
* pipeline_job_id
* framework
* test_suite
* total_tests
* passed_tests
* failed_tests
* skipped_tests
* duration_ms

### test_failures

* id
* test_run_id
* test_name
* test_file
* failure_message
* stack_trace
* failure_signature
* status
* created_at

### log_artifacts

* id
* pipeline_job_id
* object_storage_key
* content_hash
* byte_size
* redaction_status
* created_at
* retention_until

---

## 15.4 Triage Tables

### triage_cases

* id
* project_id
* test_failure_id
* status
* human_review_status
* assigned_user_id
* created_at
* updated_at

### triage_findings

* id
* triage_case_id
* model_run_id
* summary
* category
* severity
* priority
* probable_owner
* probable_cause
* recommended_action
* confidence
* created_at

### triage_evidence

* id
* triage_finding_id
* evidence_type
* source_id
* excerpt
* relevance_score
* line_start
* line_end

### related_incidents

* id
* triage_case_id
* related_defect_id
* similarity_score
* retrieval_rank

---

## 15.5 Defect Tables

### defects

* id
* project_id
* external_defect_id
* title
* description
* category
* severity
* priority
* status
* owning_team
* root_cause
* resolution
* created_at
* resolved_at

### defect_links

* id
* source_defect_id
* target_defect_id
* relationship_type
* confidence

---

## 15.6 Test-Generation Tables

### test_generation_requests

* id
* project_id
* user_id
* source_type
* source_reference
* framework
* configuration
* status
* created_at

### generated_test_cases

* id
* request_id
* title
* objective
* preconditions
* test_data
* steps
* expected_result
* priority
* tags
* generated_code
* schema_valid
* syntax_valid
* duplicate_score
* execution_status
* human_status
* created_at

---

## 15.7 Knowledge Tables

### knowledge_documents

* id
* project_id
* title
* document_type
* source
* version
* object_storage_key
* content_hash
* status
* access_scope
* created_at
* updated_at

### knowledge_chunks

* id
* document_id
* chunk_index
* content
* token_count
* metadata
* embedding
* created_at

The embedding column will use pgvector.

---

## 15.8 AI Governance Tables

### model_runs

* id
* provider
* model
* operation
* prompt_version_id
* input_token_count
* output_token_count
* latency_ms
* estimated_cost
* status
* error_code
* created_at

### prompt_versions

* id
* prompt_name
* version
* template
* schema_version
* status
* created_by
* created_at

### feedback

* id
* user_id
* entity_type
* entity_id
* rating
* corrected_fields
* comments
* created_at

### evaluation_runs

* id
* dataset_id
* model
* prompt_version
* configuration
* metrics
* status
* created_at

### audit_logs

* id
* organisation_id
* user_id
* action
* entity_type
* entity_id
* metadata
* ip_address
* created_at

---

# 16. API Design

All APIs will be versioned.

Base path:

```text
/api/v1
```

## 16.1 CI and Build APIs

```http
POST /integrations/github/webhook
GET  /pipeline-runs
GET  /pipeline-runs/{run_id}
GET  /pipeline-runs/{run_id}/jobs
GET  /pipeline-runs/{run_id}/failures
POST /pipeline-runs/{run_id}/analyse
```

## 16.2 Failure APIs

```http
GET   /failures
GET   /failures/{failure_id}
POST  /failures/{failure_id}/analyse
POST  /failures/{failure_id}/assign
POST  /failures/{failure_id}/feedback
GET   /failures/{failure_id}/similar
```

## 16.3 Test-Generation APIs

```http
POST /test-generation/requests
GET  /test-generation/requests/{request_id}
GET  /test-generation/requests/{request_id}/tests
POST /generated-tests/{test_id}/approve
POST /generated-tests/{test_id}/reject
POST /generated-tests/{test_id}/regenerate
POST /generated-tests/{test_id}/validate
```

## 16.4 Triage APIs

```http
POST /triage-cases
GET  /triage-cases
GET  /triage-cases/{case_id}
POST /triage-cases/{case_id}/run
PATCH /triage-cases/{case_id}
POST /triage-cases/{case_id}/approve
POST /triage-cases/{case_id}/feedback
```

## 16.5 Knowledge APIs

```http
POST   /knowledge/documents
GET    /knowledge/documents
GET    /knowledge/documents/{document_id}
POST   /knowledge/documents/{document_id}/reindex
PATCH  /knowledge/documents/{document_id}
DELETE /knowledge/documents/{document_id}
POST   /knowledge/search
```

## 16.6 Evaluation APIs

```http
POST /evaluations
GET  /evaluations
GET  /evaluations/{evaluation_id}
GET  /evaluations/{evaluation_id}/results
```

## 16.7 Job APIs

```http
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
GET  /jobs/{job_id}/events
```

## 16.8 Administrative APIs

```http
GET   /admin/prompts
POST  /admin/prompts
POST  /admin/prompts/{prompt_id}/activate
GET   /admin/providers
PATCH /admin/providers/{provider_id}
GET   /admin/audit-logs
```

---

# 17. API Standards

Every endpoint will use:

* Authentication
* Authorisation
* Request validation
* Consistent error structure
* Correlation IDs
* Trace IDs
* Pagination
* Filtering
* Rate limiting
* Audit logging where required
* OpenAPI documentation

Standard error format:

```json
{
  "error": {
    "code": "TRIAGE_ANALYSIS_FAILED",
    "message": "The triage analysis could not be completed.",
    "request_id": "req_7b34e",
    "details": {}
  }
}
```

Public API errors must not expose:

* Stack traces
* Database details
* Provider credentials
* Internal file paths
* Unredacted logs

---

# 18. AI Provider Gateway

The AI provider gateway will isolate the application from a specific vendor.

Interfaces:

```python
class LanguageModelProvider:
    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
    ) -> StructuredGenerationResponse:
        ...
```

```python
class EmbeddingProvider:
    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        ...
```

Provider-gateway responsibilities:

* Authentication
* Request formatting
* Timeout handling
* Retry handling
* Structured-output validation
* Token counting
* Cost estimation
* Model fallback
* Provider-health checks
* Circuit breaking
* Logging
* Metrics
* Rate limiting

Domain modules will call the gateway rather than a provider SDK directly.

---

# 19. Prompt Management

Prompts will be version-controlled application assets.

Each prompt version will include:

* Name
* Version
* Purpose
* Input schema
* Output schema
* Prompt template
* Safety instructions
* Example inputs
* Example outputs
* Compatible models
* Evaluation results
* Activation status

Prompt changes must not be deployed directly to production without evaluation.

Prompt lifecycle:

```text
Draft
  ↓
Offline evaluation
  ↓
Review
  ↓
Staging
  ↓
Limited release
  ↓
Active
  ↓
Deprecated
```

---

# 20. RAG Pipeline

## 20.1 Ingestion Flow

```text
Document upload
  ↓
File validation
  ↓
Text extraction
  ↓
Normalisation
  ↓
Sensitive-data redaction
  ↓
Metadata extraction
  ↓
Chunking
  ↓
Embedding generation
  ↓
Vector storage
  ↓
Index verification
```

## 20.2 Retrieval Flow

```text
User or system query
  ↓
Query normalisation
  ↓
Metadata-filter construction
  ↓
Query embedding
  ↓
Vector search
  ↓
Keyword search
  ↓
Candidate combination
  ↓
Optional reranking
  ↓
Context assembly
  ↓
LLM generation
  ↓
Evidence validation
```

## 20.3 Retrieval Controls

The retrieval layer must support:

* Project isolation
* Access-scope filtering
* Date filtering
* Document-type filtering
* Repository filtering
* Service filtering
* Minimum relevance threshold
* Maximum context size
* Duplicate-chunk removal
* Source diversity

The system should return "insufficient evidence" rather than generate unsupported conclusions.

---

# 21. Log-Analysis Pipeline

```text
Raw CI logs
  ↓
Store immutable original
  ↓
Decode and normalise
  ↓
Redact sensitive values
  ↓
Detect log format
  ↓
Collapse repeated lines
  ↓
Extract stack traces
  ↓
Extract error events
  ↓
Identify first meaningful failure
  ↓
Generate failure signature
  ↓
Retrieve similar incidents
  ↓
Generate structured summary
  ↓
Validate evidence
  ↓
Persist triage result
```

Failure signature inputs may include:

* Exception type
* Normalised error message
* Failed test name
* Service name
* HTTP status
* Top stack frames
* Dependency name

Dynamic values such as timestamps, IDs, and random ports will be removed from signatures.

---

# 22. Test-Generation Pipeline

```text
Requirement or API specification
  ↓
Input validation
  ↓
Requirement decomposition
  ↓
Entity and constraint extraction
  ↓
Risk identification
  ↓
Test-plan generation
  ↓
Detailed test generation
  ↓
Code generation
  ↓
Structured validation
  ↓
Duplicate detection
  ↓
Static analysis
  ↓
Sandbox execution
  ↓
Human review
```

## 22.1 Requirement Decomposition

The system will identify:

* Actors
* Preconditions
* Actions
* Business rules
* State transitions
* Success conditions
* Failure conditions
* Data constraints
* Security constraints
* Integration dependencies

## 22.2 Generated-Test Validation

Validation levels:

1. JSON/schema validation
2. Required-field validation
3. Framework syntax validation
4. Import validation
5. Duplicate detection
6. Safety scanning
7. Optional sandbox execution

Generated code that fails validation will not be presented as production-ready.

---

# 23. Code-Execution Sandbox

Generated test code must not execute directly inside the API or worker container.

Sandbox requirements:

* Separate ephemeral container
* No privileged mode
* Read-only base filesystem
* CPU limits
* Memory limits
* Execution timeout
* No access to platform secrets
* No access to internal metadata services
* Network disabled by default
* Explicit allowlist for required destinations
* Temporary working directory
* Complete cleanup after execution

Execution output will be treated as untrusted input.

---

# 24. Defect-Triage Pipeline

```text
Failure selected
  ↓
Failure metadata loaded
  ↓
Relevant logs loaded
  ↓
Failure signature created
  ↓
Historical defects retrieved
  ↓
Runbooks retrieved
  ↓
Classification generated
  ↓
Ownership recommended
  ↓
Severity recommended
  ↓
Root-cause hypothesis generated
  ↓
Evidence mapped
  ↓
Confidence calculated
  ↓
Human review
```

The system must distinguish:

* Confirmed facts
* Retrieved historical information
* AI-generated hypotheses
* Human-approved conclusions

The UI must not visually present hypotheses as established facts.

---

# 25. Confidence Scoring

The confidence score should not be copied directly from an LLM response.

It should combine signals such as:

* Retrieval similarity
* Number of supporting sources
* Source agreement
* Historical classification accuracy
* Model output consistency
* Presence of deterministic error indicators
* Human-feedback history

Example:

```text
Final confidence =
0.30 × retrieval quality
+ 0.25 × evidence agreement
+ 0.20 × classifier confidence
+ 0.15 × historical accuracy
+ 0.10 × output consistency
```

The exact formula will be calibrated using evaluation data.

---

# 26. Security Architecture

## 26.1 Authentication

Use OpenID Connect or OAuth-based identity.

Local development may support a controlled development identity provider.

## 26.2 Authorisation

Role-based access control:

* Engineer
* Quality Engineer
* QE Lead
* Platform Engineer
* Administrator

Permissions will be checked at both:

* API-route level
* Service/business-logic level

## 26.3 Secret Management

Secrets will be stored in:

* Cloud secret manager
* Kubernetes secrets backed by encryption
* Local `.env` files only for development

Secrets must never appear in:

* Application logs
* AI prompts
* API responses
* Frontend state
* Git commits

## 26.4 Data Encryption

* TLS for network communication
* Database encryption at rest
* Object-storage encryption
* Encrypted integration credentials
* Restricted backup access

## 26.5 Sensitive-Data Redaction

The system will detect:

* API keys
* Access tokens
* Bearer tokens
* Passwords
* Session cookies
* Email addresses
* IP addresses where required
* Credit-card patterns
* Private keys
* Database connection strings
* Cloud credentials

Redaction methods:

* Pattern matching
* Entropy detection
* Named-entity recognition where appropriate
* Configurable organisation-specific patterns

## 26.6 Prompt-Injection Protection

Documents and logs will be treated as untrusted data.

Controls:

* Clear separation between system instructions and retrieved context
* Retrieved text enclosed as data
* No execution of commands contained in documents
* No tool use based solely on retrieved instructions
* Output schema enforcement
* External-action allowlists
* Human approval for mutations
* Prompt-injection pattern detection

## 26.7 File Upload Security

Controls:

* File-size limits
* Allowed MIME types
* File-extension validation
* Content sniffing
* Archive-depth limits
* Malware scanning where available
* Object-storage isolation
* Safe extraction libraries
* Filename normalisation

## 26.8 API Security

* Rate limiting
* Request-size limits
* Input validation
* CORS restrictions
* CSRF protection where applicable
* Secure cookies
* Webhook signature validation
* Idempotency keys
* Dependency scanning
* Security headers

---

# 27. GitHub Actions Integration

## 27.1 Webhook Events

Initial events:

* Workflow run completed
* Check run completed
* Pull request updated
* Push completed

## 27.2 Webhook Validation

The backend will:

1. Read the delivery ID.
2. Validate the signature.
3. Reject expired or malformed requests.
4. Check duplicate delivery IDs.
5. Store minimal delivery metadata.
6. Queue processing.
7. Return quickly.

Webhook processing must be idempotent.

## 27.3 CI Analysis Workflow

```text
GitHub workflow fails
  ↓
Webhook sent
  ↓
Signature verified
  ↓
Pipeline metadata stored
  ↓
Logs and test reports retrieved
  ↓
Analysis job queued
  ↓
Logs redacted and processed
  ↓
Triage recommendation generated
  ↓
Dashboard updated
  ↓
Optional GitHub check summary posted
```

The initial project will post informational summaries only. It will not block merges unless a human explicitly configures that behaviour in a future version.

---

# 28. Observability

## 28.1 Logging

Use structured JSON logs.

Required fields:

* Timestamp
* Service
* Environment
* Severity
* Message
* Request ID
* Trace ID
* User ID where permitted
* Project ID
* Job ID
* Event type
* Error code

## 28.2 Metrics

API metrics:

* Request count
* Request latency
* Error rate
* Rate-limit events

Worker metrics:

* Queue depth
* Job-processing time
* Retry count
* Failure count
* Timeout count

AI metrics:

* Provider latency
* Token usage
* Cost
* Structured-output failures
* Retry count
* Fallback count

RAG metrics:

* Retrieval latency
* Average similarity
* No-result rate
* Reranking latency
* Citation coverage

Business metrics:

* Mean triage time
* Acceptance rate
* Generated-test approval rate
* Ownership-prediction accuracy
* Similar-defect retrieval accuracy

## 28.3 Tracing

Distributed traces will cover:

```text
Frontend request
→ API
→ database
→ Redis
→ worker
→ AI provider
→ object storage
```

## 28.4 Alerts

Alerts:

* API error rate above threshold
* Worker unavailable
* Queue backlog above threshold
* Database unavailable
* Redis unavailable
* AI-provider failure rate
* Webhook-processing failures
* Cost threshold exceeded
* Excessive job timeout rate

---

# 29. Reliability Requirements

The platform will implement:

* Graceful degradation
* Provider timeouts
* Retry policies
* Circuit breakers
* Dead-letter queue
* Database connection pooling
* Health checks
* Readiness checks
* Liveness checks
* Idempotent processing
* Backup and restore procedure
* Migration rollback process
* Controlled feature flags

When the AI provider is unavailable:

* Existing results remain accessible.
* Manual workflows continue.
* New analysis jobs remain queued or fail cleanly.
* The UI displays provider status.
* The system does not return fabricated results.

---

# 30. Performance Targets

Initial engineering targets:

* Standard read API p95 latency below 500 ms
* Search API p95 latency below 1.5 seconds
* Webhook acknowledgement below 2 seconds
* Small log analysis completed within 60 seconds
* Test-generation job completed within 90 seconds
* Dashboard initial load below 3 seconds under normal development conditions
* Support at least 25 concurrent active users
* Support at least 100 queued background jobs
* Maintain API availability during worker restarts

These are initial targets, not guaranteed production service-level agreements.

---

# 31. Data Retention

Suggested defaults:

* Raw CI logs: 30 days
* Redacted logs: 90 days
* Triage findings: 1 year
* Audit logs: 1 year
* Generated tests: retained until deleted
* Model-run metadata: 1 year
* Temporary uploaded files: 24 hours after processing
* Failed job payloads: 14 days

Retention must be configurable.

Deletion workflows must remove:

* Database records
* Object-storage files
* Search indexes
* Embeddings
* Cached data

---

# 32. Testing Strategy

## 32.1 Unit Tests

Coverage:

* Domain logic
* Parsers
* Redaction
* Failure signatures
* Confidence calculations
* Schema validation
* Permission checks
* Prompt assembly
* Retrieval filters

## 32.2 Integration Tests

Coverage:

* PostgreSQL
* pgvector
* Redis
* Object storage
* Worker execution
* GitHub webhook processing
* AI-provider adapter
* Authentication

## 32.3 Contract Tests

Coverage:

* Frontend-to-backend contracts
* CLI-to-backend contracts
* GitHub webhook payloads
* AI structured outputs
* External integration schemas

## 32.4 End-to-End Tests

Critical flows:

1. User logs in.
2. User uploads a requirement.
3. System generates tests.
4. User approves a test.
5. GitHub workflow failure is ingested.
6. System analyses logs.
7. System retrieves similar defects.
8. User reviews triage.
9. User submits feedback.

## 32.5 AI Evaluation Tests

Use fixed datasets to measure:

* Classification accuracy
* Severity accuracy
* Ownership accuracy
* Root-cause relevance
* Retrieval precision
* Retrieval recall
* Citation correctness
* Hallucination rate
* Test coverage quality
* Test-code validity

## 32.6 Security Tests

* Authentication bypass attempts
* Authorisation boundary tests
* Webhook forgery
* Malicious file upload
* Prompt injection
* Secret leakage
* SQL injection
* Cross-site scripting
* Path traversal
* SSRF
* Unsafe generated-code execution

## 32.7 Performance Tests

* API load
* Queue saturation
* Large-log processing
* Concurrent document ingestion
* Vector-search latency
* Dashboard query performance

---

# 33. AI Evaluation Framework

A serious AI platform requires reproducible evaluation.

## 33.1 Evaluation Dataset

Create:

* 100 historical defect examples
* 75 CI failure examples
* 50 log-summarisation examples
* 50 requirement-to-test examples
* 25 prompt-injection examples
* 25 insufficient-evidence examples

## 33.2 Defect-Triage Metrics

* Category accuracy
* Severity accuracy
* Owner accuracy
* Root-cause relevance
* Duplicate-detection precision
* Duplicate-detection recall
* Mean reciprocal rank
* Evidence correctness

## 33.3 Test-Generation Metrics

* Requirement coverage
* Valid schema percentage
* Syntax validity
* Execution success
* Duplicate rate
* Human approval rate
* Negative-case coverage
* Boundary-case coverage

## 33.4 Log-Summary Metrics

* Root-cause retention
* Critical-detail retention
* Compression ratio
* Unsupported-statement rate
* Human usefulness score

## 33.5 Release Gate

A new prompt or model configuration must not be promoted when it:

* Reduces critical classification accuracy.
* Increases hallucination rate above threshold.
* Removes evidence references.
* Significantly increases cost without measurable benefit.
* Fails structured-output validation beyond the allowed threshold.

---

# 34. CI/CD Pipeline

## 34.1 Pull-Request Checks

Every pull request will run:

* Formatting
* Linting
* Type checking
* Unit tests
* Integration tests
* API schema validation
* Database migration validation
* Frontend build
* Dependency vulnerability scan
* Container build
* Secret scan

## 34.2 Main-Branch Pipeline

The main branch will:

1. Run all quality checks.
2. Build versioned containers.
3. Generate software bill of materials.
4. Scan container images.
5. Push images to registry.
6. Deploy to development.
7. Run smoke tests.
8. Require approval for staging.
9. Run staging end-to-end tests.

## 34.3 Database Migrations

Requirements:

* Forward-only production migrations where possible
* Backward-compatible application deployment
* Migration dry run
* Backup before high-risk migration
* Explicit rollback procedure

---

# 35. Deployment Architecture

## 35.1 Local Development

Docker Compose services:

```text
frontend
api
worker
scheduler
postgres
redis
minio
```

## 35.2 Kubernetes Deployment

Kubernetes resources:

* Frontend Deployment
* API Deployment
* Worker Deployment
* Scheduler Deployment
* Services
* Ingress
* ConfigMaps
* Secrets
* Horizontal Pod Autoscalers
* Pod disruption budgets
* Network policies
* Persistent storage where required

## 35.3 AWS Reference Architecture

* Route 53
* CloudFront
* Application Load Balancer
* EKS or ECS
* RDS PostgreSQL
* ElastiCache Redis
* S3
* Secrets Manager
* CloudWatch
* OpenTelemetry collector
* Container registry
* Web application firewall

For the master's project, a smaller deployment may use:

* One frontend container
* One API container
* One worker container
* Managed PostgreSQL
* Managed Redis
* S3-compatible storage

---

# 36. Repository Structure

```text
qe-copilot/
├── apps/
│   ├── api/
│   ├── worker/
│   ├── scheduler/
│   ├── cli/
│   └── web/
│
├── packages/
│   ├── auth/
│   ├── common/
│   ├── database/
│   ├── ci_ingestion/
│   ├── log_analysis/
│   ├── test_generation/
│   ├── defect_triage/
│   ├── knowledge/
│   ├── retrieval/
│   ├── ai_gateway/
│   ├── prompt_registry/
│   ├── feedback/
│   ├── evaluation/
│   ├── observability/
│   └── security/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── end_to_end/
│   ├── performance/
│   └── evaluation/
│
├── datasets/
│   ├── ci_failures/
│   ├── defects/
│   ├── requirements/
│   ├── runbooks/
│   └── expected_outputs/
│
├── infrastructure/
│   ├── docker/
│   ├── kubernetes/
│   ├── helm/
│   └── terraform/
│
├── scripts/
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── security/
│   ├── operations/
│   └── decisions/
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── package.json
├── README.md
└── LICENSE
```

---

# 37. Development Standards

Backend:

* Type hints required
* Pydantic models for API boundaries
* Repository pattern for data access
* Explicit transaction boundaries
* No business logic in route handlers
* No provider calls directly from controllers
* No silent exception handling
* Structured error codes
* Minimum automated-test threshold
* Database queries reviewed for indexes and N+1 problems

Frontend:

* TypeScript strict mode
* Shared API client
* Accessible components
* Loading, empty, error, and partial states
* No business rules duplicated from backend
* Consistent form validation
* Error boundaries
* End-to-end coverage of critical flows

---

# 38. Project Implementation Plan

## Phase 0: Foundation

Deliverables:

* Final architecture
* Repository setup
* Coding standards
* Docker environment
* CI pipeline
* Database baseline
* Authentication design
* Initial frontend shell

## Phase 1: Core Platform

Deliverables:

* User and project management
* Repository configuration
* Job framework
* Worker service
* Audit logging
* System health
* Base frontend navigation

## Phase 2: Test Generation

Deliverables:

* Requirement input
* Test-generation API
* Structured AI output
* Generated-test storage
* Test Generator dashboard
* Test editing and approval
* Pytest code generation
* Static validation

## Phase 3: CI Integration

Deliverables:

* GitHub webhook integration
* Workflow metadata ingestion
* Log retrieval
* Test-report parsing
* CI Failures dashboard
* Failure Detail page

## Phase 4: Log Analysis

Deliverables:

* Log normalisation
* Redaction
* Error extraction
* Failure signatures
* AI summaries
* Evidence mapping
* Human feedback

## Phase 5: RAG and Defect Triage

Deliverables:

* Knowledge ingestion
* Chunking
* Embeddings
* Vector search
* Similar-defect retrieval
* Triage recommendations
* Confidence scoring
* Defect Triage dashboard

## Phase 6: Evaluation

Deliverables:

* Evaluation datasets
* Automated AI evaluations
* Prompt comparison
* Evaluation dashboard
* Accuracy and retrieval metrics
* Release gates

## Phase 7: Production Hardening

Deliverables:

* Rate limiting
* Provider fallback
* Circuit breaker
* Full observability
* Security tests
* Performance tests
* Kubernetes manifests
* Terraform
* Backup and recovery documentation

## Phase 8: Final Demonstration

Deliverables:

* Complete streaming-platform sample dataset
* End-to-end demo
* Architecture diagrams
* Benchmark report
* Security report
* API documentation
* Deployment guide
* Demo video
* Resume metrics

---

# 39. Priority Classification

## P0 — Required

* FastAPI backend
* Next.js dashboard
* PostgreSQL
* Background jobs
* Test generation
* CI log ingestion
* Log summarisation
* Defect triage
* RAG
* Similar-defect search
* Human feedback
* Docker
* GitHub Actions
* Unit and integration tests
* Sensitive-data redaction

## P1 — Strongly Recommended

* CLI
* Kubernetes deployment
* Model fallback
* Evaluation dashboard
* Prompt versioning
* OpenTelemetry
* Role-based access
* Generated-code sandbox
* Analytics

## P2 — Optional Extensions

* Jira integration
* Slack notifications
* Multi-provider routing
* Automated pull-request creation
* Fine-tuned classifier
* Real-time collaborative review
* Advanced reranking
* Multi-tenant billing or quotas

---

# 40. Demonstration Scenario

The final demo should use a synthetic streaming platform with services such as:

* Authentication service
* Subscription service
* Entitlement service
* Playback service
* Profile service
* Content catalogue
* Search service
* Recommendation service

## Demo Flow

1. A product requirement is entered:

   "A subscriber should be able to resume playback on another registered device."

2. QE Copilot generates:

   * Positive tests
   * Negative tests
   * Boundary tests
   * Pytest code

3. The user approves selected tests.

4. A simulated GitHub Actions workflow executes the tests.

5. One test fails because the entitlement token expired.

6. GitHub sends a webhook to QE Copilot.

7. QE Copilot retrieves and redacts the logs.

8. The platform identifies the first meaningful failure.

9. The platform finds two similar historical incidents.

10. The platform recommends:

* Category: Entitlement
* Severity: High
* Owner: Playback Platform
* Root cause: Expired entitlement token
* Action: Review token TTL and refresh workflow

11. The engineer reviews the evidence.

12. The engineer corrects or approves the recommendation.

13. The analytics dashboard records:

* Analysis time
* Human acceptance
* Model cost
* Retrieval quality
* Final resolution

This single demonstration proves that the frontend, backend, AI, RAG, CI integration, observability, and feedback systems work together.

---

# 41. Definition of Done

The project is complete when:

* Users can authenticate and access project-scoped data.
* GitHub Actions failures can be ingested automatically.
* Raw logs are stored securely.
* Logs are redacted before AI processing.
* Failed tests are visible in the dashboard.
* AI can generate structured failure summaries.
* Similar historical defects can be retrieved.
* Triage recommendations include evidence.
* Users can correct and approve recommendations.
* Requirements can be converted into test cases.
* Generated tests can be validated.
* Long-running tasks use background jobs.
* The CLI can access core workflows.
* The frontend displays job progress.
* Core APIs are documented.
* Unit, integration, and end-to-end tests pass.
* Security controls are documented and tested.
* The platform runs through Docker Compose.
* A cloud or Kubernetes deployment is demonstrated.
* Evaluation results are documented.
* Performance metrics are measured.
* Resume claims are supported by actual project evidence.

---

# 42. Success Metrics

Do not claim impact without measuring it.

Target measurements:

* Reduction in median failure-triage time
* Correct failure-category percentage
* Correct owning-team percentage
* Similar-defect retrieval precision
* Similar-defect retrieval recall
* AI output acceptance rate
* Generated-test approval rate
* Generated-code syntax-validity rate
* Average analysis latency
* Average cost per analysis
* Percentage of outputs containing valid evidence
* Percentage of logs successfully redacted

Example final result format:

```text
Evaluated QE Copilot on 75 controlled CI failures and reduced median
triage time from 8.2 minutes to 3.1 minutes while achieving 84%
failure-category accuracy and 81% top-three similar-incident recall.
```

Only use actual measured numbers.

---

# 43. Primary Technical Risks

## Risk: Hallucinated Root Causes

Mitigation:

* Evidence requirements
* Confidence thresholds
* Structured output
* "Insufficient evidence" response
* Human approval

## Risk: Sensitive Data Leakage

Mitigation:

* Redaction
* Encryption
* Provider controls
* Audit logs
* Access restrictions

## Risk: Unreliable Generated Tests

Mitigation:

* Schema validation
* Static analysis
* Sandbox execution
* Human review
* Duplicate detection

## Risk: Provider Outages

Mitigation:

* Timeouts
* Retries
* Circuit breaker
* Provider fallback
* Queue preservation

## Risk: Excessive Project Complexity

Mitigation:

* Modular monolith
* P0/P1/P2 prioritisation
* One primary CI provider
* One primary cloud deployment
* Limited initial test frameworks

## Risk: Weak Evaluation

Mitigation:

* Fixed evaluation datasets
* Baseline comparisons
* Human-labelled expected results
* Automated regression evaluation

---

# 44. Resume Positioning

Recommended project heading:

**QE Copilot — AI-Powered Test Generation and Defect Triage Platform**

Potential resume bullets after implementation:

* Architected and developed an AI-powered quality-engineering platform using Python, FastAPI, Next.js, PostgreSQL, pgvector, Redis, and Docker to generate tests, analyse CI failures, and automate evidence-backed defect triage.

* Built a retrieval-augmented incident-analysis pipeline that indexed historical defects, runbooks, and CI logs to identify similar failures, recommend probable root causes, and predict owning engineering teams.

* Integrated GitHub Actions through signed, idempotent webhooks and asynchronous workers, enabling automated ingestion, redaction, classification, and summarisation of failed test executions.

* Designed a complete operational dashboard for CI-failure investigation, test generation, human review, AI evaluation, prompt management, system health, and quality-engineering analytics.

* Implemented provider-neutral LLM and embedding gateways with structured outputs, retries, timeouts, token tracking, model fallback, prompt versioning, and evaluation-based release controls.

* Secured AI-processing workflows using role-based access control, audit logging, secret and PII redaction, encrypted integration credentials, and isolated execution of generated tests.

The final bullet set should include verified latency, accuracy, throughput, or efficiency measurements.

---

# 45. Final Architecture Decision

The project will be implemented as:

* A Next.js frontend dashboard
* A Python FastAPI backend
* A separately deployed asynchronous worker
* PostgreSQL with pgvector
* Redis for queues and distributed coordination
* Object storage for logs and uploaded documents
* Provider-neutral LLM and embedding adapters
* GitHub Actions integration
* Docker-based local development
* Kubernetes-compatible deployment
* Comprehensive evaluation, security, testing, and observability

This architecture is technically deep, directly aligned with AI Tooling and Global Quality Engineering responsibilities, and realistic enough to be completed and demonstrated by a master's student.

The project must be presented as an engineering platform with measurable quality and reliability, not as an LLM chatbot.
