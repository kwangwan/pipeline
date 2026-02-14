# Project RAG API Manual for AI Agents

## Overview
This manual is designed for AI agents integrating with the **Project RAG** RAG service. Use this API to organize, upload, and search semantic data.

API_BASE = "https://api.proj.run"
**Authentication**: `Authorization: Bearer <API_KEY>`

---

## 1. Create Category
Creates a container for documents. Categories can be private or public.

- **Endpoint**: `POST /categories`
- **Headers**:
    - `Content-Type`: `application/json`
    - `Authorization`: `Bearer <API_KEY>`
- **Body**:
    ```json
    {
      "name": "My Knowledge Base",
      "visibility": "private" 
    }
    ```
    - `visibility`: `"public"` (default) or `"private"`.
- **Response**:
    ```json
    { "id": "uuid", "name": "...", "visibility": "..." }
    ```

## 2. Upload Document
Uploads text content for embedding.

- **Endpoint**: `POST /documents`
- **Body**:
    ```json
    {
      "categoryId": "<CATEGORY_ID>",
      "content": "Full text content...",
      "metadata": { "source": "url", "tags": ["a", "b"] },
      "date": "2023-11-01"
    }
    ```
    - `date`: (Optional) ISO 8601 string or Unix timestamp. Defaults to now.
- **Constraints**:
    - `content`: Max **2000 characters**.
    - `metadata`: Max **20,000 characters**. (JSON object)
- **Response**:
    ```json
    { "success": true, "docId": "uuid" }
    ```

## 3. List Documents
Lists documents in a specific category. Supports pagination, sorting, and search.

- **Endpoint**: `GET /documents/list`
- **Parameters**:
    - `categoryId`: (Required) Category ID.
    - `page`: (Optional) Page number (Default 1).
    - `limit`: (Optional) Items per page (Default 20, Max 100).
    - `sortBy`: (Optional) `content`, `status`, `created_at`, `record_date` (Default `created_at`).
    - `sortOrder`: (Optional) `asc` or `desc` (Default `desc`).
- **Response**:
    ```json
    {
      "documents": [
        {
          "id": "doc_uuid",
          "content": "Snippet...",
          "status": "indexed",
          "metadataCount": 5,
          "createdAt": 1700000000,
          "recordDate": 1700000000
        }
      ],
      "total": 50,
      "page": 1,
      "totalPages": 5
    }
    ```
    - `content`: **Snippet** (First 200 characters). Use `GET /documents/:docId` for full content.

    - `metadataCount`: Number of metadata fields.

## 4. Get Single Document
Retrieves the full content and metadata of a specific document.

- **Endpoint**: `GET /documents/:docId`
- **Response**:
    ```json
    {
      "id": "doc_uuid",
      "content": "Full text content...",
      "metadata": { "source": "web", "author": "Alice" },
      "createdAt": 1700000000,
      "recordDate": 1700000000,
      "status": "indexed"
    }
    ```

## 5. Update Document Metadata
Updates custom metadata for an existing document.

- **Endpoint**: `PUT /documents/:docId/metadata`
- **Body**:
    ```json
    {
      "metadata": { "source": "updated", "status": "reviewed" }
    }
    ```
- **Constraints**:
    - `metadata`: Max **20,000 characters**. (JSON object)
- **Response**:
    ```json
    { "success": true }
    ```

## 6. Update Document Date
Updates the record date of a document. Used for sorting or period-based filtering.

- **Endpoint**: `PATCH /documents/:docId/date`
- **Body**:
    ```json
    {
      "date": "2023-12-25"
    }
    ```
    - `date`: ISO 8601 date string (YYYY-MM-DD) or Unix timestamp.
- **Response**:
    ```json
    { "success": true, "recordDate": 1703462400 }
    ```

## 7. Delete Document
Deletes a document by ID.

- **Endpoint**: `DELETE /documents`
- **Body**:
    ```json
    {
      "docId": "<DOC_ID>"
    }
    ```
- **Response**:
    ```json
    { "success": true }
    ```

## 8. Query Data (Search)
Performs semantic search across documents using a **Hybrid Search Strategy**:
- **Scoped Search**: When `userIds` or `categoryIds` are provided, the system uses exact SQL filtering for **100% accuracy**.
- **Global Search**: When searching across all public data, it uses high-performance DiskANN indexing.

- **Endpoint**: `POST /query`
- **Body**:
    ```json
    {
      "query": "Search question...",
      "limit": 50,
      "filter": {
        "categoryIds": ["<CATEGORY_ID>"],
        "userIds": ["<USER_ID>"],
        "startDate": "2023-01-01",
        "endDate": "2023-12-31" 
      }
    }
    ```
- **Parameters**:
    - `limit`: (Optional) Max results (Default 20, Max 100).
- **Filter Parameters**:
    - `categoryIds`: (Optional) Array of Category IDs. Providing these triggers **High-Accuracy Scoped Search**.
    - `userIds`: (Optional) Array of User IDs.
- **Response**:
    ```json
    {
      "results": [
        {
          "id": "doc_uuid",
          "score": 0.89,
          "snippet": "First 200 characters of the document...",
          "metadataCount": 3,
          "userId": "user_uuid",
          "username": "alice",
          "categoryId": "cat_uuid",
          "categoryName": "My Knowledge Base",
          "visibility": "private",
          "createdAt": "2023-11-01T12:00:00.000Z",
          "date": "2023-11-01T12:00:00.000Z"
        }
      ]
    }
    ```
    - `score`: Similarity score (0.0 - 1.0). Calculated as `1.0 - cosine_distance`.
    - `snippet`: First 200 characters of the document content. Use `GET /documents/:id` for full content.
    - `metadataCount`: Number of metadata fields. Use `GET /documents/:id` for full metadata.

> **Tip**: The search API returns lightweight snippets for fast response. To get full content and metadata for a specific result, follow up with `GET /documents/:id`.

---

## 9. Full Workflow Example

Complete lifecycle: Create → Upload → Search → Get Full Content.

```python
import requests
import time

API_BASE = "https://api.proj.run"
HEADERS = {"Authorization": "Bearer <API_KEY>"}

# 1. Create a Category
cat = requests.post(f"{API_BASE}/categories", json={
    "name": "My Knowledge Base",
    "visibility": "private"
}, headers=HEADERS).json()
cat_id = cat["id"]
print(f"Category created: {cat_id}")

# 2. Upload a Document
doc = requests.post(f"{API_BASE}/documents", json={
    "categoryId": cat_id,
    "content": "Project RAG is a powerful serverless RAG platform built on Cloudflare.",
    "metadata": {"source": "manual", "tags": ["tech", "rag"]},
    "date": "2023-11-01"
}, headers=HEADERS).json()
print(f"Document uploaded: {doc['docId']}")

# 3. Wait for embedding processing
time.sleep(2)

# 4. Search (returns snippets, not full content)
results = requests.post(f"{API_BASE}/query", json={
    "query": "What is a powerful RAG platform?",
    "filter": {"categoryIds": [cat_id]}
}, headers=HEADERS).json()

for r in results["results"]:
    print(f"[Score: {r['score']:.3f}] {r['snippet']}")
    print(f"  Metadata fields: {r['metadataCount']}")

    # 5. Get full content & metadata for each result
    detail = requests.get(
        f"{API_BASE}/documents/{r['id']}",
        headers=HEADERS
    ).json()
    print(f"  Full content: {detail['content']}")
    print(f"  Metadata: {detail['metadata']}")
```

---

## Usage Quotas
- **Uploads**: 100 requests / week (Free plan)
- **Queries**: 100 requests / week (Free plan)
- **Character Limits**:
    - **User Search**: 20 chars
    - **Document Search**: 2000 chars

## Error Codes
- `400`: Bad Request (Invalid JSON, Limits Exceeded, Invalid Characters)
- `401`: Unauthorized (Invalid/Missing Key)
- `403`: Forbidden (Access Denied to Category)
- `409`: Conflict (Duplicate Pending Report)
- `429`: Quota Exceeded
