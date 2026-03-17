# Candor Database Schema

## Tables

### Core Entities
- elections
- candidates
- candidate_elections

### Pledges
- pledges
- pledge_nodes
- pledge_node_progress
- pledge_node_progress_sources
- pledge_node_sources
- pledge_votes

### Sources
- sources

### Community
- user_profiles
- contributor_stats
- reports

### Misc
- terms

## user_profiles

User profile information for the platform.

| column | type | default | description |
|------|------|------|------|
| user_id | uuid (PK) |  | Reference to auth.users.id |
| role | text | 'user' | User role (user, admin, etc.) |
| status | text | 'active' | Account status |
| reputation_score | int4 | 0 | User reputation score |
| created_at | timestamptz | now() | Account creation time |
| updated_at | timestamptz | now() | Last update time |
| nickname | text | NULL | Display nickname |

**Primary Key**
- user_id

**Relationships**
- `user_id` → `auth.users.id`

## candidates

Stores basic information about political candidates.

| column | type | default | description |
|------|------|------|------|
| id | uuid (PK) | gen_random_uuid() | Unique identifier for the candidate |
| name | text | NULL | Candidate name |
| birth_date | date | NULL | Candidate date of birth |
| image | text | NULL | Candidate image URL |
| description | text | NULL | Candidate description or profile |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |
## candidate_elections

Links candidates to specific elections.  
A candidate can participate in multiple elections.

| column | type | default | description |
|------|------|------|------|
| id | int8 (PK) |  | Unique identifier |
| candidate_id | uuid | NULL | Reference to candidate |
| election_id | int8 | NULL | Reference to election |
| result | text | NULL | Election result (e.g. win, lose) |
| is_elect | bool | NULL | Whether the candidate was elected |
| created_at | timestamptz | now() | Record creation time |
| party | text | NULL | Political party |
| candidate_number | int8 | NULL | Ballot number |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `candidate_id` → `candidates.id`
- `election_id` → `elections.id`
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`

## elections

Stores information about elections.

| column | type | default | description |
|------|------|------|------|
| id | int8 (PK) |  | Unique identifier for the election |
| election_type | text | NULL | Type of election (e.g. presidential, parliamentary, local) |
| title | text | NULL | Election name or title |
| election_date | date | NULL | Date of the election |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`


## pledge_node_progress

Stores evaluation results for a specific pledge node.

| column | type | default | description |
|------|------|------|------|
| id | uuid (PK) | gen_random_uuid() | Unique identifier |
| pledge_node_id | uuid | NULL | Reference to pledge node |
| progress_rate | numeric | NULL | Progress percentage (0–100) |
| status | text | NULL | Progress status (e.g. planned, in_progress, completed, failed) |
| reason | text | NULL | Explanation of the evaluation |
| evaluator | text | NULL | Person or organization evaluating the progress |
| evaluation_date | date | NULL | Date of evaluation |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `pledge_node_id` → `pledge_nodes.id`
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`

## pledge_node_progress_sources

Stores sources used to support evaluations of pledge progress.

| column | type | default | description |
|------|------|------|------|
| id | uuid (PK) | gen_random_uuid() | Unique identifier |
| pledge_node_progress_id | uuid | NULL | Reference to progress evaluation |
| source_id | uuid | NULL | Reference to source |
| source_role | text | NULL | Role of the source (e.g. evidence, reference) |
| quoted_text | text | NULL | Quoted excerpt from the source |
| page_no | text | NULL | Page number or location in the source |
| note | text | NULL | Additional notes |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |

**Primary Key**
- `id`

**Relationships**
- `pledge_node_progress_id` → `pledge_node_progress.id`
- `source_id` → `sources.id`
- `created_by` → `user_profiles.user_id`

## pledge_node_sources

Stores sources that support the content of a pledge node.

| column | type | default | description |
|------|------|------|------|
| id | int8 (PK) |  | Unique identifier |
| pledge_node_id | uuid | NULL | Reference to pledge node |
| pledge_id | uuid | NULL | Reference to pledge |
| source_id | uuid | NULL | Reference to source |
| source_role | text | NULL | Role of the source (e.g. pledge_document, news, report) |
| note | text | NULL | Additional notes about the source |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |

**Primary Key**
- `id`

**Relationships**
- `pledge_node_id` → `pledge_nodes.id`
- `pledge_id` → `pledges.id`
- `source_id` → `sources.id`
- `created_by` → `user_profiles.user_id`
## pledge_nodes

Stores the hierarchical structure of pledges.  
Each pledge is organized as a tree (Goal → Promise → Item).

| column | type | default | description |
|------|------|------|------|
| id | uuid (PK) | gen_random_uuid() | Unique identifier |
| pledge_id | uuid | NULL | Reference to pledge |
| name | text | NULL | Short title of the node |
| content | text | NULL | Full text of the pledge node |
| level | int4 | NULL | Node level (1=goal, 2=promise, 3=item) |
| parent_id | uuid | NULL | Parent node (self-referencing tree structure) |
| sort_order | int4 | 0 | Order of nodes within the same level |
| is_leaf | bool | NULL | Whether this node is a leaf node |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `pledge_id` → `pledges.id`
- `parent_id` → `pledge_nodes.id`
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`

## pledges

Stores top-level pledge information made by candidates in a specific election.

| column | type | default | description |
|------|------|------|------|
| id | uuid (PK) | gen_random_uuid() | Unique identifier |
| title | text | NULL | Title of the pledge |
| raw_text | text | NULL | Original pledge text |
| category | text | NULL | Policy category |
| fulfillment_rate | int4 | 0 | Overall fulfillment rate (%) |
| status | text | 'active' | Pledge status |
| candidate_election_id | int8 | NULL | Reference to candidate election |
| sort_order | int2 | NULL | Display order |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `candidate_election_id` → `candidate_elections.id`
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`

## reports

Stores user reports about candidates, pledges, or other content.

| column | type | default | description |
|------|------|------|------|
| id | int8 (PK) |  | Unique identifier |
| user_id | uuid | NULL | User who submitted the report |
| candidate_id | uuid | NULL | Reported candidate |
| pledge_id | uuid | NULL | Reported pledge |
| report_type | text | NULL | Type of report (candidate, pledge, etc.) |
| reason_category | text | NULL | Category of report reason |
| reason | text | NULL | Detailed report reason |
| target_url | text | NULL | URL of the reported content |
| status | text | NULL | Report status (pending, reviewed, resolved) |
| created_at | timestamptz | now() | Report creation time |
| updated_at | timestamptz | NULL | Last update time |
| admin_note | text | NULL | Internal note by admin |
| resolved_at | timestamptz | NULL | Time when report was resolved |
| resolved_by | uuid | NULL | Admin who resolved the report |

**Primary Key**
- `id`

**Relationships**
- `user_id` → `user_profiles.user_id`
- `candidate_id` → `candidates.id`
- `pledge_id` → `pledges.id`
- `resolved_by` → `user_profiles.user_id`

## sources

Stores external references used to support pledges and evaluations.

| column | type | default | description |
|------|------|------|------|
| id | uuid (PK) | gen_random_uuid() | Unique identifier |
| title | text | NULL | Title of the source |
| url | text | NULL | Source URL |
| source_type | text | NULL | Type of source (news, report, government_document, etc.) |
| publisher | text | NULL | Publisher or organization |
| published_at | date | NULL | Publication date |
| summary | text | NULL | Summary of the source |
| note | text | NULL | Additional notes |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`

## terms

Stores information about a candidate's term in office for a specific election.

| column | type | default | description |
|------|------|------|------|
| id | int8 (PK) |  | Unique identifier |
| candidate_id | uuid | NULL | Reference to candidate |
| election_id | int8 | NULL | Reference to election |
| position | text | NULL | Position held after the election |
| term_start | date | NULL | Start date of the term |
| term_end | date | NULL | End date of the term |
| is_current | bool | NULL | Whether this is the current active term |
| created_at | timestamptz | now() | Record creation time |
| created_by | uuid | NULL | User who created the record |
| updated_at | timestamptz | NULL | Last update time |
| updated_by | uuid | NULL | User who last updated the record |

**Primary Key**
- `id`

**Relationships**
- `candidate_id` → `candidates.id`
- `election_id` → `elections.id`
- `created_by` → `user_profiles.user_id`
- `updated_by` → `user_profiles.user_id`
