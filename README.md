# Ask Testudo

A student-facing Retrieval-Augmented Generation (RAG) chat tool for University of Maryland (UMD) students to query academic policies, course requirements, and registration procedures. 

The project features a ChatGPT-style full-page interface with UMD branding. It is built as a full-stack application with a Python backend and a React frontend.

## Architecture

- **Backend**: FastAPI with a Pinecone vector database using Cohere and xAI for generation and embeddings. Located in the root directory. Ready for deployment on Railway.
- **Frontend**: Next.js application with Tailwind CSS and shadcn/ui. Located in the `frontend` directory. Ready for deployment on Vercel.

## Setup & Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- Pinecone, Cohere, and xAI API keys
- Tesseract and Poppler (for ingestion, optional if just running the API)

### Environment Variables

Create a `.env` file in the root directory for the backend:

```env
COHERE_API_KEY=your_key_here
PINECONE_API_KEY=your_key_here
PINECONE_INDEX_NAME=ask-testudo
XAI_API_KEY=your_key_here
```

Create a `.env.local` file in the `frontend` directory for the frontend:

```env
NEXT_PUBLIC_API_URL=http://localhost:8002
```

### Running the Backend

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the FastAPI server:
   ```bash
   uvicorn query:app --port 8002 --reload
   ```
   The backend will run on `http://localhost:8002`.

### Running the Frontend

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
   The website will run on `http://localhost:3000`.

## Deployment

- **Backend (Railway)**: Connect the GitHub repository to Railway and add the environment variables. The included `Procfile` will handle starting the FastAPI server.
- **Frontend (Vercel)**: Connect the `frontend` folder to Vercel and add `NEXT_PUBLIC_API_URL` to the environment variables. The build settings should automatically use Next.js.

## Data Ingestion

To ingest new PDFs into the vector database, use the `ingest.py` script. The ingestion pipeline handles document loading, chunking, embedding, and upserting data to Pinecone. Run `verify_ingestion.py` to test the stored documents in the index.
