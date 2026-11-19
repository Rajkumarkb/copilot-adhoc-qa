# AlertBus QA App Model

## Overview
- AlertBus Dashboard reviews stop-arm events and evidence, manages citations/payments/legal workflows, runs reports/jobs, and administers users/partners. [inferred]
- Configured QA target: `https://qa-alertbus-dashboard.aws.buspatrol.com`; use only the configured QA host. [inferred]
- Modules: authentication, home/queues, events, event processing, reports, legal/citations/payments/dockets, jobs, admin, and Fast Access Evidence (FAE).
- Roles used by QA specs:
  - Admin (base QA account): specs use admin surfaces to create/edit partners and manage users/roles; explicit denied actions are not established.
  - Approver: can open approval, UTC approval, and affirmation queues and approve/disapprove citations; denial boundaries are not established.
  - Manager: can view/search legal citations, payments, dockets, and events; the manager spec asserts the New Docket button is absent.
  - Processor: can process events with and without violations and create citations; denied actions are not established.
  - Reviewer: can mark review events as violation, no violation, or unreviewable and stop reviewing; denied actions are not established.
  - Supervisor: can inspect/filter the supervisor queue, update citation details/comments, and approve/reject citations; denied actions are not established.
- Observed routes include `/`, `/login`, `/events`, `/events/:id`, `/citations`, `/payments`, `/dockets`, `/users`, `/partners`, `/qa_events`, and `/video-requests`; other routes are navigation-derived.
- Sources: `qa/qa.config.yaml`, `qa/knowledge/framework-inventory.md`, and the specs cited below.

## Journeys
1. Citation lifecycle: pending approval → claim → approve or disapprove; UTC approval has a separate pending queue and approval/disapproval flow; affirmation has separate add/reject flows; legal follow-up schedules a hearing and moves a citation to `Pend Hearing`, then docket flows create/edit/print or close/reopen a docket. These are separate specs and do not assert one citation traversing every stage. Sources: `tests/ui/applications/qa/alertbus/regression/home/approver-queues/approver-queue-new.spec.ts`, `utc-approval-queue.spec.ts`, `affirmation-queue.spec.ts`, `tests/ui/applications/qa/alertbus/regression/legal/citations/hearing.spec.ts`, and `tests/ui/applications/qa/alertbus/regression/legal/dockets/dockets.spec.ts`.
2. Jobs: create a print job → confirm creation → open its job detail and inspect status → pending-correction status allows validation regeneration, while printing status exposes PDF download. Source: `tests/ui/applications/qa/alertbus/regression/jobs/print-jobs-new.spec.ts`; `pages/alertbus/jobs/new-print-jobs.ts`.
3. Admin user/partner: create a QA user or partner → edit/update → verify in the same record or list. Partner API tests create, retain the returned ID, edit/update, and re-read it; user creation has an enabled edge test, but the UI create-then-edit test is commented out and the API Users spec is commented out. Sources: `tests/api/applications/qa/alertbus/regression/admin/Partner.spec.ts`, `tests/ui/applications/qa/alertbus/edge-case/admin/users.spec.ts`, `tests/ui/applications/qa/alertbus/regression/admin/users.spec.ts`, and `tests/api/applications/qa/alertbus/regression/admin/Users.spec.ts`.
4. Citation payment: open `/citations`, filter by partner and `Due`, open an eligible citation, select Violator View, open it in a new tab, then choose Pay by Card or Bank. Stripe Card (Alpha) completes payment and verifies confirmation, `Paid`, `$0.00` balance, and payment entries. Stripe ACH (Alpha) covers OAuth and non-OAuth test institutions and expects a pending confirmation. Velocity and Paymentus (Omega) specs switch the partner payment portal and navigate to their card forms, but do not enter card data or submit. Full-balance-only policy is team knowledge; Payments/report specs do not reconcile totals to a payment transaction. Sources: `tests/ui/applications/qa/alertbus/regression/legal/citations/violator-view/stripe-card.spec.ts`, `stripe-bank.spec.ts`, `velocity.spec.ts`, `paymentus.spec.ts`, `tests/ui/applications/qa/alertbus/regression/legal/payments/payment.spec.ts`, and `tests/ui/applications/qa/alertbus/regression/reports/payments.spec.ts`.

## Module: Authentication
- Routes/controls: `/login`, `/`; login form and privacy/terms links.
- Expected results:
  - Invalid username error contains `We couldn't find an account with that username.` [asserted: `tests/ui/applications/qa/alertbus/regression/auth/login-page.spec.ts`; `pages/alertbus/auth/login-page.ts`]
  - Invalid password error contains `Your account or password is incorrect. If you don't remember your password,` [asserted: same spec and page object]
- Automated coverage: Login page, invalid credentials, footer links.
- Adhoc gaps: Session expiry/renewal, deep-link restoration, multi-tab logout, and MFA are not established by these AlertBus specs.

## Module: Home and Queues
- Routes/controls: `/`; pending approval, approval, UTC approval, and affirmation queues; role-specific review/processing entry points.
- Expected results:
  - Partner-filtered approval rows all match the selected partner; registration-filtered rows match the selected registration status. [asserted: `tests/ui/applications/qa/alertbus/regression/home/approver-queues/approver-queue-new.spec.ts`]
  - Supported page sizes are 10, 25, 50, and 75; rendered count is at most page size, API page size matches selection, and row count is `min(page size, total count)`. [asserted: same spec; `pages/alertbus/home/approval-page/approval/approval-page-new.ts`]
  - Claim, approve, and disapprove actions show `Successfully Claimed Citation`, `Successfully Approved Citation`, and `Successfully Disapproved Citation`. [asserted: same spec]
  - UTC approval displays `Citation saved.`; bulk approval reports `1 UTC(s) approved, 0 failed.` [asserted: `tests/ui/applications/qa/alertbus/regression/home/approver-queues/utc-approval-queue.spec.ts`; `pages/alertbus/home/approval-page/utc-approval/utc-approval-page.ts`]
- Automated coverage: Queue filters/sorting/pagination, comments, claims, approval/disapproval, UTC, affirmation, and role-specific review.
- Adhoc gaps: Cross-role authorization, stale/repeated submissions, and queue/detail/report reconciliation.

## Module: Events Management
- Routes/controls: `/events`, `/events/:id`; partner search, date-range type, status, and optional violation-side filters.
- Expected results:
  - Event links use `/events/<numeric id>`; detail title is `Event: <id>` and identifies the selected event. [asserted: `tests/api/applications/qa/alertbus/regression/AlertBusEvents.spec.ts`]
  - Partner search results identify the selected partner. [asserted: same spec]
  - Date filters include Reviewed at, Processed at, Event At, and DB entry at; status filters include Reviewable, Unreviewable, Processable, Approvable, In Review, and No violation. [asserted: `tests/ui/applications/qa/alertbus/regression/events/events.spec.ts`]
- Automated coverage: List/search/detail, filters, and navigation to event processing.
- Adhoc gaps: Date boundaries, filter persistence, pagination consistency, and detail evidence availability.

## Module: Event Processing
- Routes/controls: `/qa_events` is observed; Processable Events, QA Processable Events, Pending Registration.
- Expected results:
  - The API flow claims a processable event, creates a citation, and asserts the response has an ID. [asserted: `tests/api/applications/qa/alertbus/regression/ProcessedEvents2.spec.ts`]
  - Processed event details show the selected result as `Violation` or `No Violation`. [asserted: `tests/ui/applications/qa/alertbus/regression/home/processor-role.spec.ts`]
  - A simulated submission network failure displays `Failed to create citation`; the spec then retries after restoring connectivity. [asserted: `tests/ui/applications/qa/event-processing/edge-case/processable-events.spec.ts`]
- Automated coverage: Landing pages, event processing, citation creation, registration lookup, comments, and submission failure.
- Adhoc gaps: Duplicate retry behavior and event/citation/report consistency.

## Module: Reports
- Routes/controls: Reports navigation; Event Rejections, Citations, Payments, Approvals, Hearings, Pending Hearings.
- Expected results:
  - Payments report headings include Success Count/Amount, Web/Walkin/Mail payment Count/Amount, Check/Card/Cash/Ach Count/Amount, `Money Order`, Refund Count/Amount, and Failed Count. [asserted: `tests/ui/applications/qa/alertbus/regression/reports/payments.spec.ts`; `pages/alertbus/reports/payments-reports.ts`]
  - Payment report money fields are displayed as currency. [asserted: same spec and page object]
  - Invalid/mismatched report dates show `We're sorry, but something went wrong.` [asserted: `tests/ui/applications/qa/alertbus/edge-case/reports/payments.spec.ts`]
  - The API report suite expects HTTP 200 for covered reports; event-report generation is skipped in QA. [asserted: `tests/api/applications/qa/alertbus/regression/reports/Reports.spec.ts`]
- Automated coverage: Report queries, response/column checks, money display, malformed dates.
- Adhoc gaps: No assertion reconciles report totals to a payment/citation record or filtered source rows; date/time-zone boundaries.

## Module: Legal, Citations, Payments, and Dockets
- Routes/controls: `/citations`, `/payments`, `/dockets`; citation detail tabs, Violator View, hearings, adjudication, and dockets.
- Expected results:
  - Successful card payment confirmation includes citation number and the payment/processing-fee amounts; citation status becomes `Paid`, balance becomes `$0.00`, and new `Payment` and `Processing Fee` entries match the computed amounts. [asserted: `tests/ui/applications/qa/alertbus/regression/legal/citations/violator-view/stripe-card.spec.ts`]
  - Hearing creation shows `Hearing was successfully created.` and citation status becomes `Pend Hearing`. [asserted: `tests/ui/applications/qa/alertbus/regression/legal/citations/hearing.spec.ts`]
  - Invalid hearing data shows `We're sorry, but something went wrong.` [asserted: `tests/ui/applications/qa/alertbus/edge-case/legal/citations/hearing.spec.ts`]
  - Docket close/reopen messages are `The docket has been closed.` and `The docket has been re-opened.` [asserted: `tests/ui/applications/qa/alertbus/regression/legal/dockets/dockets.spec.ts`]
  - A repeated Apply Payment attempt within five minutes is blocked with reason matching `Created at cannot be within <n> seconds of another payment on the same citation.` [asserted: `tests/ui/applications/qa/alertbus/regression/legal/citations/actions/apply-payment.spec.ts`; `pages/alertbus/citations/specific-citation/actions-tab.ts`]
- Automated coverage: Citation search/details, payment, hearing/adjudication, and docket CRUD/status workflows.
- Adhoc gaps: Required full-balance policy across every payment route, Payments-list/receipt/report total reconciliation, malformed searches, and document recovery.

## Module: Jobs
- Routes/controls: Jobs pages reached through navigation; print, UTC print, citation/event export, collections, undeliverable, late notice, lease/rental, and registration-flag jobs.
- Expected results:
  - New print job creation shows `Your print job has been created`. [asserted: `tests/ui/applications/qa/alertbus/regression/jobs/print-jobs-new.spec.ts`; `pages/alertbus/jobs/new-print-jobs.ts`]
  - A `Pending corrections` job exposes validation regeneration; starting it shows `Your print job validations are being generated`. [asserted: same spec and page object]
  - A `Printing` job exposes the PDF download button. [asserted: same page object]
  - Document-job request feedback is `The job you requested will be emailed to you.` [asserted: `tests/api/applications/qa/alertbus/regression/AlertBusDocumentsJobs.spec.ts`]
- Automated coverage: Job creation, status/detail navigation, filters/sorting, selected cancellation and downloads.
- Adhoc gaps: Retry/deduplication, partial failures, completed-result persistence, and job/source-record reconciliation.

## Module: Admin
- Routes/controls: `/users`, `/partners`; roles, partner details/settings/geofences, significant events, payment imports.
- Expected results:
  - Blank email error is `Emailcan't be blank`; blank phone error is `Phone Numbercan't be blank`; blank first or last name error is `UserBoth first name and last name are required.` [asserted: `tests/ui/applications/qa/alertbus/edge-case/admin/users.spec.ts`]
  - User creation accepts 70-character first/middle/last names and shows the created-user success message; the generated email is capped at 255 characters, but the spec does not test that boundary. [asserted: same spec]
  - Partner create API returns status `success` and an ID; edit/update is followed by a read of that same ID. [asserted: `tests/api/applications/qa/alertbus/regression/admin/Partner.spec.ts`]
  - Empty partner name leaves Submit disabled; the 256-character name test asserts HTTP 500. [asserted: `tests/ui/applications/qa/alertbus/regression/admin/create-partner.spec.ts`; `tests/ui/applications/qa/alertbus/edge-case/admin/create-partner.spec.ts`]
  - User create/edit UI flow and API Users tests are commented out; do not count them as executable end-to-end coverage. [asserted: `tests/ui/applications/qa/alertbus/regression/admin/users.spec.ts`; `tests/api/applications/qa/alertbus/regression/admin/Users.spec.ts`]
- Automated coverage: Partner API create/read/edit/update/settings/activation; UI partner create/edit and user required/max-length validation.
- Adhoc gaps: User create→edit→verify on the same new record, role-permission matrix, duplicate user behavior, and shared-setting impact.

## Module: Fast Access Evidence
- Routes/controls: FAE video-request UI; inventory observes `/video-requests` and `/fae/`. FAE API service fetches lists, vehicles, labels, creates/deletes requests, downloads, and streams video.
- Expected results:
  - New request with two labels produces two table rows when split-by-label is enabled and one row when disabled. [asserted: `tests/ui/applications/qa/fae/regression/new-video-request.spec.ts`]
  - Submit is disabled with no inputs; unknown vehicle and label searches show `No Vehicles Found` and `No results found`. [asserted: same spec]
  - Future dates are disabled; a duration over the supported limit shows an error containing `This request exceeds the limit by`. [asserted: same spec]
  - API list has `active`, `old`, and `expiring` arrays with typed request fields; deletion returns `success: true` and identifies the deleted request. [asserted: `tests/api/applications/qa/fae/regression/FastAccessEvidenceAPI.spec.ts`]
  - Video stream response contains typed request metadata and video URL/channel/labels. [asserted: same spec]
- Automated coverage: FAE UI request creation/validation plus API list, vehicle/label lookup, create/delete, download/stream. No FAE page-object entry is listed in the inventory.
- Adhoc gaps: UI/API record consistency, request lifecycle/status transitions, and download failure recovery.

## Test data
- Fixtures: `@tests/ui/base/fixtures/alertbus`, `@tests/ui/base/fixtures/fae`, `@tests/ui/base/fixtures/event-processing`.
- Aliases: `PARTNERS.alpha`, `PARTNERS.omega`, `USERS.reviewer2`, `partnerData`, `testDataPartners`, and `citationData`.
- Event citations: `ProcessedEvents2.spec.ts` uses `EventManagementApiService.claimEvent` followed by `createCitation`.
- FAE requests: `FastAccessEvidenceApiService.createVideoRequest` and the UI `NewRequestPage` create request records using fixture-selected vehicle/label data.
- Admin records: partner API tests retain `createdPartnerId` for follow-up reads/edits; UI specs generate user/partner identifiers at runtime.
- Job records: print-job specs create jobs through the UI and open the resulting job detail.

## API to UI map
| API service/method exposed by test | Screen/action | Evidence and limits |
| --- | --- | --- |
| `AlertBusEvent.eventListResponse`, `singleEventsResponse` | Events list/detail | `tests/api/applications/qa/alertbus/regression/AlertBusEvents.spec.ts`; verifies selected event identity. |
| `AlertBusLegalApiService.searchCitationResponse` | Citation search/results | `tests/api/applications/qa/alertbus/regression/AlertBusLegalCitations.spec.ts`; raw endpoint not shown. |
| `addCitationCommentsResponse`, `uploadCitationDocument`, `deleteDocumentCitation` | Citation Details/Documents | Same spec; mutations. |
| `AlertBusReportsApiService.fetch*Report` | Reports screens | `tests/api/applications/qa/alertbus/regression/reports/Reports.spec.ts`; response/schema checks, not transaction reconciliation. |
| `AlertBusAdminApiService` partner methods | Admin partner screens | `tests/api/applications/qa/alertbus/regression/admin/Partner.spec.ts`; geofence update is skipped. |
| `FastAccessEvidenceApiService` | FAE request list/create/delete/download/stream | `tests/api/applications/qa/fae/regression/FastAccessEvidenceAPI.spec.ts`. |

## Do-not-touch
- Never leave the configured QA host or interact with production hosts listed in `qa/qa.config.yaml`.
- Ask before approval/affirmation/rejection, payments/refunds, sending/publishing, imports/uploads, export/email actions, cancellation/deletion, bulk jobs, or other irreversible/external actions; follow `approval_required_keywords`.
- Do not change shared/global configuration or edit records not created for the current run; created records must use the active run prefix.
- Do not include credentials, email addresses, phone numbers, license plates, tokens, payment details, or other personal data in notes/model output.
- Do not run the automation framework or call its APIs during adhoc QA.