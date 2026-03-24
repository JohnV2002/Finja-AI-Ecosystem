async def _is_duplicate_candidate(self, mem: dict, use_openai: bool, openai_embs: list, existing_texts: list, existing_vecs_local: Optional[np.ndarray]) -> tuple[bool, Optional[np.ndarray]]:
    content = mem.get('content', '').strip()
    if not content:
        return (True, existing_vecs_local)
    norm = self._normalize_text(content)
    if use_openai and await self._is_openai_duplicate(norm, openai_embs, content):
        return (True, existing_vecs_local)
    if self.valves.use_local_embedding_fallback:
        is_dup, existing_vecs_local = await self._is_local_embedding_duplicate(norm, existing_vecs_local, existing_texts, content)
        if is_dup:
            return (True, existing_vecs_local)
    if self._is_levenshtein_duplicate(norm, existing_texts, content):
        return (True, existing_vecs_local)
    return (False, existing_vecs_local)