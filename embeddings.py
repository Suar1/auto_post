import openai
import json
import numpy as np
from pathlib import Path
import logging
from typing import List, Dict, Tuple, Optional
import sqlite3
import re

# Constants
EMBEDDINGS_FILE = 'topic_embeddings.json'
SIMILARITY_THRESHOLD = 0.92
EMBEDDING_MODEL = "text-embedding-ada-002"

def normalize_text(text: str) -> str:
    """Normalize text for comparison (similar to normalize_title in services.py)."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    
    # Remove markdown heading markers
    text = re.sub(r'^#+\s+', '', text)
    
    # Remove "Title:" prefix
    text = re.sub(r'^title:\s*', '', text, flags=re.IGNORECASE)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip().lower()
    
    return text

def get_embedding(text: str, user_id: int) -> Optional[List[float]]:
    """Get embedding for a text using OpenAI's API."""
    try:
        # Get user's OpenAI API key
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT openai_api_key FROM user_settings WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        user_api_key = str(result[0]) if result and result[0] is not None else ""
        conn.close()
        
        if not user_api_key:
            logging.error(f"No OpenAI API key set for user {user_id}")
            return None
            
        client = openai.OpenAI(api_key=user_api_key)
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logging.error(f"Failed to get embedding: {e}")
        return None

def load_embeddings() -> Dict[str, List[float]]:
    """Load embeddings from JSON file."""
    try:
        if Path(EMBEDDINGS_FILE).exists():
            with open(EMBEDDINGS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logging.error(f"Failed to load embeddings: {e}")
        return {}

def save_embeddings(embeddings: Dict[str, List[float]]) -> bool:
    """Save embeddings to JSON file."""
    try:
        with open(EMBEDDINGS_FILE, 'w') as f:
            json.dump(embeddings, f)
        return True
    except Exception as e:
        logging.error(f"Failed to save embeddings: {e}")
        return False

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def is_similar_to_existing(text: str, user_id: int) -> Tuple[bool, Optional[str]]:
    """
    Check if text is semantically similar to any existing topics.
    Returns (is_similar, most_similar_topic).
    """
    # Skip short or empty texts
    if not text or len(text) < 10:
        logging.warning(f"[semantic_check] Text '{text}' is too short for semantic comparison")
        return False, None
    
    # Normalize the text for better comparison
    normalized_text = normalize_text(text)
    
    # Get embedding for normalized text
    new_embedding = get_embedding(normalized_text, user_id)
    if not new_embedding:
        logging.error(f"[semantic_check] Failed to get embedding for '{normalized_text}'")
        return False, None
        
    # Load existing embeddings
    embeddings = load_embeddings()
    if not embeddings:
        logging.info(f"[semantic_check] No existing embeddings to compare with")
        return False, None
        
    # Check similarity with all existing topics
    max_similarity = 0
    most_similar_topic = None
    
    similarities = {}
    for topic, embedding in embeddings.items():
        # Normalize stored topics as well for fair comparison
        normalized_topic = normalize_text(topic)
        
        if normalized_topic == normalized_text:
            logging.warning(f"[semantic_check] Exact normalized match: '{text}' == '{topic}'")
            return True, topic
            
        similarity = cosine_similarity(new_embedding, embedding)
        similarities[topic] = similarity
        if similarity > max_similarity:
            max_similarity = similarity
            most_similar_topic = topic
    
    # Sort similarities and log top 3 matches
    sorted_similarities = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
    top_matches = sorted_similarities[:3]
    
    for topic, score in top_matches:
        logging.info(f"[semantic_check] Similarity of '{text}' with '{topic}': {score:.3f}")
            
    # Log the comparison
    logging.warning(f"[semantic_check] Comparing '{text}' to existing topics. Max similarity: {max_similarity:.3f} with '{most_similar_topic}'")
    is_similar = max_similarity > SIMILARITY_THRESHOLD
    
    if is_similar:
        logging.warning(f"[semantic_check] SIMILARITY DETECTED ({max_similarity:.3f} > {SIMILARITY_THRESHOLD}) between '{text}' and '{most_similar_topic}'")
    else:
        logging.info(f"[semantic_check] No similar topics found for '{text}'")
    
    return is_similar, most_similar_topic

def add_embedding(text: str, user_id: int) -> bool:
    """Add a new embedding to the storage."""
    embedding = get_embedding(text, user_id)
    if not embedding:
        return False
        
    embeddings = load_embeddings()
    embeddings[text] = embedding
    return save_embeddings(embeddings)

def update_embeddings_from_db(user_id: int) -> bool:
    """Update embeddings storage with all topics from the database."""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT title FROM user_posts WHERE user_id = ?', (user_id,))
        titles = [row[0] for row in c.fetchall()]
        conn.close()
        
        embeddings = load_embeddings()
        updated = False
        
        for title in titles:
            if title not in embeddings:
                embedding = get_embedding(title, user_id)
                if embedding:
                    embeddings[title] = embedding
                    updated = True
                    
        if updated:
            return save_embeddings(embeddings)
        return True
    except Exception as e:
        logging.error(f"Failed to update embeddings from DB: {e}")
        return False

def cleanup_embeddings(user_id: int) -> bool:
    """Remove embeddings for posts that no longer exist in the database."""
    try:
        # Get all current post titles
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT title FROM user_posts WHERE user_id = ?', (user_id,))
        current_titles = {row[0] for row in c.fetchall()}
        conn.close()
        
        # Load embeddings
        embeddings = load_embeddings()
        if not embeddings:
            return True
            
        # Remove embeddings for non-existent posts
        removed = False
        for title in list(embeddings.keys()):
            if title not in current_titles:
                del embeddings[title]
                removed = True
                
        if removed:
            return save_embeddings(embeddings)
        return True
    except Exception as e:
        logging.error(f"Failed to cleanup embeddings: {e}")
        return False

def get_similarity_stats(text: str, user_id: int) -> Dict[str, float]:
    """Get similarity scores for a text against all existing topics."""
    new_embedding = get_embedding(text, user_id)
    if not new_embedding:
        return {}
        
    embeddings = load_embeddings()
    if not embeddings:
        return {}
        
    similarities = {}
    for topic, embedding in embeddings.items():
        similarity = cosine_similarity(new_embedding, embedding)
        similarities[topic] = similarity
        
    return dict(sorted(similarities.items(), key=lambda x: x[1], reverse=True))

def get_embedding_stats() -> Dict[str, int]:
    """Get statistics about stored embeddings."""
    embeddings = load_embeddings()
    return {
        'total_embeddings': len(embeddings),
        'unique_topics': len(set(embeddings.keys())),
        'file_size': Path(EMBEDDINGS_FILE).stat().st_size if Path(EMBEDDINGS_FILE).exists() else 0
    } 