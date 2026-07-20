"""
ingestion/ingest.py
----------------------
Builds (or rebuilds) the FAISS vector index from every supported document
under knowledge_base/raw/: .md, .txt, .html, .pdf, .docx.

This is idempotent and safe to re-run: it always rebuilds the index from
scratch from the current contents of knowledge_base/raw/, and records each
source file in the `knowledge_documents` table for the admin dashboard.

Usage:
    python ingestion/ingest.py
"""
import hashlib
import sys
from pathlib import Path

from langchain_community.document_loaders import (
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
    UnstructuredHTMLLoader,
)
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

sys.path.append(str(Path(__file__).resolve().parent.parent))  # allow `config`, `services` imports

from config.settings import get_settings
from database.models import KnowledgeDocument
from database.session import db_session, init_db
from services.embedding_service import get_embedding_model

settings = get_settings()
KB_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "raw"

LOADERS = {
    ".md": TextLoader,
    ".txt": TextLoader,
    ".html": UnstructuredHTMLLoader,
    ".htm": UnstructuredHTMLLoader,
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_front_matter(text: str) -> tuple[dict, str]:
    """Very small YAML-ish front-matter parser for our own .md files (source_url, title)."""
    meta = {}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            block = text[3:end].strip().splitlines()
            for line in block:
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip()
            text = text[end + 3 :].strip()
    return meta, text


def load_documents() -> list[Document]:
    docs: list[Document] = []
    if not KB_DIR.exists():
        print(f"No knowledge base directory found at {KB_DIR}", file=sys.stderr)
        return docs

    files = [p for p in KB_DIR.rglob("*") if p.is_file() and p.suffix.lower() in LOADERS]
    print(f"Found {len(files)} source file(s) in {KB_DIR}")

    with db_session() as db:
        db.query(KnowledgeDocument).delete()  # rebuild the tracking table from scratch

        for path in files:
            loader_cls = LOADERS[path.suffix.lower()]
            try:
                if path.suffix.lower() in (".md", ".txt"):
                    raw_text = path.read_text(encoding="utf-8")
                    meta, body = _extract_front_matter(raw_text)
                    loaded = [Document(page_content=body, metadata={})]
                else:
                    loaded = loader_cls(str(path)).load()
                    meta = {}
            except Exception as exc:  # noqa: BLE001
                print(f"  ! Failed to load {path.name}: {exc}", file=sys.stderr)
                continue

            title = meta.get("title", path.stem.replace("-", " ").title())
            source_url = meta.get("source_url", "")

            for doc in loaded:
                doc.metadata.update({"title": title, "source_url": source_url, "source_file": path.name})
                docs.append(doc)

            db.add(
                KnowledgeDocument(
                    source_path=str(path.relative_to(KB_DIR.parent.parent)),
                    source_url=source_url,
                    doc_type=path.suffix.lstrip(".").lower(),
                    chunk_count=0,  # updated after splitting, below
                    checksum=_checksum(path),
                )
            )
    return docs


def main():
    init_db()
    documents = load_documents()
    if not documents:
        print("No documents to index. Add files under knowledge_base/raw/ first.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
    )
    chunks = splitter.split_documents(documents)
    print(f"Split into {len(chunks)} chunks (chunk_size={settings.CHUNK_SIZE}, overlap={settings.CHUNK_OVERLAP})")

    embeddings = get_embedding_model()
    print(f"Embedding with '{settings.EMBEDDING_MODEL}' (this may take a while on first run)...")
    vectorstore = FAISS.from_documents(chunks, embeddings)

    out_dir = Path(settings.VECTORSTORE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(out_dir))
    print(f"FAISS index saved to {out_dir}")

    # Update per-source chunk counts for the admin dashboard.
    counts: dict[str, int] = {}
    for c in chunks:
        counts[c.metadata.get("source_file", "")] = counts.get(c.metadata.get("source_file", ""), 0) + 1

    with db_session() as db:
        for kd in db.query(KnowledgeDocument).all():
            fname = Path(kd.source_path).name
            kd.chunk_count = counts.get(fname, 0)

    print("Ingestion complete. Call POST /api/v1/admin/knowledge-base/reload to hot-reload the API.")


if __name__ == "__main__":
    main()
