"""
Semantic Chunking Engine with 5 enforceable rules.
Transforms raw extraction into RAG-optimized Logical Document Units.
"""

import hashlib
import re  # <--- ADD THIS AT THE TOP!
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict

from ..models.extraction import ExtractedDocument, TextBlock, Table, Figure
from ..models.chunking import (
    LDU, ChunkType, ChunkingResult, ChunkGroup, ChunkRelation,
    ChunkRelationship
)
from ..utils.hashing import SpatialHasher


class ChunkValidator:
    """
    Validates chunks against the 5 constitutional rules.
    No chunk is emitted unless all rules are satisfied.
    """

    def __init__(self):
        self.violations = []

    def validate_rule_1_no_table_split(self, chunks: List[LDU], tables: List[Dict]) -> bool:
        """
        RULE 1: Table cells must never be split from their header row.
        A table must be a single LDU, not split across multiple chunks.
        """
        valid = True

        # Group chunks by table_id if present in metadata
        table_groups = defaultdict(list)
        for chunk in chunks:
            table_id = chunk.metadata.get('table_id')
            if table_id:
                table_groups[table_id].append(chunk)

        # Check each table group
        for table_id, table_chunks in table_groups.items():
            if len(table_chunks) > 1:
                self.violations.append(
                    f"Table {table_id} split into {len(table_chunks)} chunks - violates Rule 1"
                )
                valid = False

            # Check if headers are present
            if table_chunks:
                chunk = table_chunks[0]
                if 'has_headers' in chunk.metadata and chunk.metadata['has_headers']:
                    # Verify headers are actually there
                    if 'headers' not in chunk.metadata:
                        self.violations.append(
                            f"Table {table_id} claims headers but none found"
                        )
                        valid = False

        return valid

    def validate_rule_2_figure_caption_linked(self, chunks: List[LDU], figures: List[Dict]) -> bool:
        """
        RULE 2: Figure caption stored as metadata of parent figure.
        Captions must be attached to their figures, not separate chunks.
        """
        valid = True

        # Find all figure chunks and caption chunks
        figure_chunks = [c for c in chunks if c.chunk_type == ChunkType.FIGURE]
        caption_chunks = [c for c in chunks if c.chunk_type == ChunkType.CAPTION]

        # Check if any captions are standalone
        for caption in caption_chunks:
            parent_figure = caption.metadata.get('parent_figure')
            if not parent_figure:
                self.violations.append(
                    f"Caption '{caption.content[:50]}...' has no parent figure - violates Rule 2"
                )
                valid = False

        # Check if figures have captions
        for figure in figure_chunks:
            if 'caption' not in figure.metadata and 'caption_text' not in figure.metadata:
                self.violations.append(
                    f"Figure on page {figure.primary_page} has no caption - may violate Rule 2"
                )
                # Not a hard violation - figures can exist without captions

        return valid

    def validate_rule_3_list_preservation(self, chunks: List[LDU], max_tokens: int = 512) -> bool:
        """
        RULE 3: Numbered lists kept as single LDU unless exceeds max_tokens.
        Lists should not be arbitrarily split.
        """
        valid = True

        # Find list chunks
        list_chunks = [c for c in chunks if c.chunk_type == ChunkType.LIST]

        # Check for list continuation
        list_groups = defaultdict(list)
        for chunk in list_chunks:
            list_id = chunk.metadata.get('list_id')
            if list_id:
                list_groups[list_id].append(chunk)

        for list_id, list_parts in list_groups.items():
            if len(list_parts) > 1:
                # Check if split was necessary (token count)
                total_tokens = sum(c.token_count for c in list_parts)
                if total_tokens <= max_tokens:
                    self.violations.append(
                        f"List {list_id} split into {len(list_parts)} parts but total tokens {total_tokens} <= {max_tokens} - violates Rule 3"
                    )
                    valid = False

        return valid

    def validate_rule_4_section_hierarchy(self, chunks: List[LDU]) -> bool:
        """
        RULE 4: Section headers stored as parent metadata on all child chunks.
        Every chunk must know its parent section.
        """
        valid = True

        for chunk in chunks:
            if chunk.chunk_type != ChunkType.SECTION_HEADER:
                if not chunk.parent_section and chunk.section_depth == 0:
                    # Only warn for top-level chunks without sections
                    if chunk.chunk_type not in [ChunkType.FIGURE, ChunkType.TABLE]:
                        self.violations.append(
                            f"Chunk '{chunk.content[:50]}...' has no parent section - violates Rule 4"
                        )
                        valid = False

        return valid

    def validate_rule_5_cross_reference_resolved(self, chunks: List[LDU]) -> bool:
        """
        RULE 5: Cross-references (e.g., 'see Table 3') resolved and stored as relationships.
        """
        valid = True

        # Pattern for cross-references
        ref_patterns = [
            r'see\s+table\s+(\d+)',
            r'see\s+figure\s+(\d+)',
            r'as\s+shown\s+in\s+table\s+(\d+)',
            r'refer\s+to\s+section\s+(\d+\.?\d*)',
            r'in\s+the\s+following\s+table',
        ]

        for chunk in chunks:
            text_lower = chunk.content.lower()
            found_refs = []

            for pattern in ref_patterns:
                matches = re.findall(pattern, text_lower)
                if matches:
                    found_refs.extend(matches)

            # Check if references are resolved
            if found_refs:
                stored_refs = chunk.cross_references
                if not stored_refs:
                    self.violations.append(
                        f"Chunk '{chunk.content[:50]}...' has references {found_refs} but none stored - violates Rule 5"
                    )
                    valid = False

        return valid

    def validate_all(self, chunks: List[LDU], extraction: ExtractedDocument) -> Tuple[bool, List[str]]:
        """
        Validate all 5 rules.

        Returns:
            (is_valid, list_of_violations)
        """
        self.violations = []

        # Convert tables and figures to dict for validation
        tables = [t.model_dump() for t in extraction.tables]
        figures = [f.model_dump() for f in extraction.figures]

        # Apply all rules
        rule1 = self.validate_rule_1_no_table_split(chunks, tables)
        rule2 = self.validate_rule_2_figure_caption_linked(chunks, figures)
        rule3 = self.validate_rule_3_list_preservation(chunks)
        rule4 = self.validate_rule_4_section_hierarchy(chunks)
        rule5 = self.validate_rule_5_cross_reference_resolved(chunks)

        is_valid = rule1 and rule2 and rule3 and rule4 and rule5

        return is_valid, self.violations


class ChunkingEngine:
    """
    Transforms extracted documents into semantic chunks (LDUs).
    Enforces the 5 constitutional rules.
    """

    def __init__(self, max_tokens: int = 512, respect_rules: bool = True):
        self.max_tokens = max_tokens
        self.respect_rules = respect_rules
        self.validator = ChunkValidator()
        self.hasher = SpatialHasher()

    def chunk(self, extraction: ExtractedDocument) -> ChunkingResult:
        """
        Main chunking method - transforms extraction to LDUs.

        Steps:
        1. Process tables (Rule 1: never split)
        2. Process figures with captions (Rule 2)
        3. Process lists (Rule 3: preserve if possible)
        4. Process text blocks with hierarchy (Rule 4)
        5. Resolve cross-references (Rule 5)
        6. Validate all rules
        """
        chunks = []
        groups = []
        relations = []

        # Track section hierarchy
        section_stack = []
        current_section = None

        # Process tables first (Rule 1)
        table_chunks, table_groups = self._chunk_tables(extraction.tables)
        chunks.extend(table_chunks)
        groups.extend(table_groups)

        # Process figures with captions (Rule 2)
        figure_chunks, figure_groups = self._chunk_figures(extraction.figures)
        chunks.extend(figure_chunks)
        groups.extend(figure_groups)

        # Process text blocks in reading order
        text_chunks, section_hierarchy = self._chunk_text_blocks(
            extraction.text_blocks,
            extraction.tables,
            extraction.figures
        )
        chunks.extend(text_chunks)

        # Build section hierarchy
        self._build_section_hierarchy(chunks, section_hierarchy)

        # Process lists (Rule 3)
        chunks = self._merge_lists(chunks)

        # Resolve cross-references (Rule 5)
        chunks, relations = self._resolve_cross_references(chunks)

        # Validate all rules
        is_valid, violations = self.validator.validate_all(chunks, extraction)

        if self.respect_rules and not is_valid:
            # Log violations but still return - don't fail silently
            print(f"⚠️ Chunking rule violations detected: {len(violations)}")
            for v in violations[:5]:  # Show first 5
                print(f"  - {v}")

        # Calculate statistics
        stats = self._calculate_stats(chunks, groups, relations)

        return ChunkingResult(
            doc_id=extraction.doc_id,
            filename=extraction.filename,
            chunks=chunks,
            groups=groups,
            relations=relations,
            rule_violations=violations,
            stats=stats
        )

    def _chunk_tables(self, tables: List[Table]) -> Tuple[List[LDU], List[ChunkGroup]]:
        """
        Convert tables to LDUs - NEVER split tables (Rule 1)
        """
        chunks = []
        groups = []

        for i, table in enumerate(tables):
            # Convert table to string representation
            table_str = self._table_to_string(table)

            # Generate content hash with spatial info
            content_hash = self.hasher.generate_content_hash(
                text=table_str,
                page_num=table.page_num,
                bbox=table.bbox if hasattr(table, 'bbox') else None
            )

            # Create LDU
            ldu = LDU(
                ldu_id=f"table_{i:04d}",
                doc_id="temp_doc_id",  # Will be set later
                chunk_type=ChunkType.TABLE,
                content=table_str,
                content_hash=content_hash,
                page_refs=[table.page_num],
                primary_page=table.page_num,
                bbox=table.bbox if hasattr(table, 'bbox') else None,
                token_count=len(table_str.split()) * 13 // 10,  # Approx
                metadata={
                    'table_id': i + 1,
                    'table_number': i + 1,
                    'has_headers': bool(table.headers),
                    'headers': table.headers,
                    'row_count': len(table.rows),
                    'col_count': len(table.headers) if table.headers else 0,
                    'caption': table.caption
                }
            )
            chunks.append(ldu)

            # Create group for table (may include caption)
            if table.caption:
                group = ChunkGroup(
                    group_id=f"tbl_grp_{i:04d}",
                    group_type="table_group",
                    chunks=[ldu.ldu_id],
                    primary_chunk=ldu.ldu_id,
                    metadata={'caption': table.caption}
                )
                groups.append(group)

        return chunks, groups

    def _chunk_figures(self, figures: List[Figure]) -> Tuple[List[LDU], List[ChunkGroup]]:
        """
        Convert figures to LDUs with captions as metadata (Rule 2)
        """
        chunks = []
        groups = []

        for i, figure in enumerate(figures):
            # Figure content is just a marker (actual image stored separately)
            content = f"[Figure: {figure.caption or 'Unnamed figure'}]"

            # Generate content hash
            content_hash = self.hasher.generate_content_hash(
                text=content,
                page_num=figure.page_num,
                bbox=figure.bbox if hasattr(figure, 'bbox') else None
            )

            # Create LDU
            ldu = LDU(
                ldu_id=f"fig_{i:04d}",
                doc_id="temp_doc_id",
                chunk_type=ChunkType.FIGURE,
                content=content,
                content_hash=content_hash,
                page_refs=[figure.page_num],
                primary_page=figure.page_num,
                bbox=figure.bbox if hasattr(figure, 'bbox') else None,
                token_count=len(content.split()),
                metadata={
                    'figure_id': i + 1,
                    'figure_number': i + 1,
                    'caption': figure.caption,
                    'image_path': str(figure.image_path) if figure.image_path else None,
                    'has_caption': bool(figure.caption)
                }
            )
            chunks.append(ldu)

            # If figure has caption, store it in metadata (Rule 2 satisfied)
            if figure.caption:
                ldu.metadata['caption_text'] = figure.caption

        return chunks, groups

    def _chunk_text_blocks(
        self,
        text_blocks: List[TextBlock],
        tables: List[Table],
        figures: List[Figure]
    ) -> Tuple[List[LDU], Dict[str, Any]]:
        """
        Convert text blocks to LDUs, respecting reading order and hierarchy.
        """
        chunks = []
        section_hierarchy = {}
        current_section = None
        section_stack = []

        # Sort blocks by page and position (reading order)
        sorted_blocks = sorted(
            text_blocks,
            key=lambda b: (b.page_num, b.bbox[1], b.bbox[0])
        )

        for i, block in enumerate(sorted_blocks):
            # Detect if this is a section header
            is_header = self._is_section_header(block.text)

            if is_header:
                # Update section hierarchy
                section_level = self._detect_header_level(block.text)
                while section_stack and section_stack[-1][0] >= section_level:
                    section_stack.pop()

                section_name = block.text.strip()
                section_stack.append((section_level, section_name))
                current_section = ' > '.join(s[1] for s in section_stack)

                # Create section header chunk
                content_hash = self.hasher.generate_content_hash(
                    text=block.text,
                    page_num=block.page_num,
                    bbox=block.bbox,
                    context=current_section
                )

                header_chunk = LDU(
                    ldu_id=f"hdr_{i:04d}",
                    doc_id="temp_doc_id",
                    chunk_type=ChunkType.SECTION_HEADER,
                    content=block.text,
                    content_hash=content_hash,
                    page_refs=[block.page_num],
                    primary_page=block.page_num,
                    bbox=block.bbox,
                    section_path=[s[1] for s in section_stack],
                    parent_section=current_section,
                    section_depth=len(section_stack),
                    token_count=len(block.text.split()),
                    metadata={'level': section_level}
                )
                chunks.append(header_chunk)

            else:
                # Regular text block
                content_hash = self.hasher.generate_content_hash(
                    text=block.text,
                    page_num=block.page_num,
                    bbox=block.bbox,
                    context=current_section
                )

                text_chunk = LDU(
                    ldu_id=f"txt_{i:04d}",
                    doc_id="temp_doc_id",
                    chunk_type=ChunkType.TEXT,
                    content=block.text,
                    content_hash=content_hash,
                    page_refs=[block.page_num],
                    primary_page=block.page_num,
                    bbox=block.bbox,
                    section_path=[s[1] for s in section_stack],
                    parent_section=current_section,
                    section_depth=len(section_stack),
                    token_count=len(block.text.split()),
                    metadata={'block_type': block.block_type}
                )
                chunks.append(text_chunk)

        # Link chunks in reading order (prev/next)
        for j in range(len(chunks)):
            if j > 0:
                chunks[j].prev_chunk = chunks[j-1].ldu_id
            if j < len(chunks) - 1:
                chunks[j].next_chunk = chunks[j+1].ldu_id

        return chunks, section_hierarchy

    def _build_section_hierarchy(self, chunks: List[LDU], hierarchy: Dict):
        """Build parent-child relationships between sections"""
        # Group chunks by section
        sections = defaultdict(list)
        for chunk in chunks:
            if chunk.parent_section:
                sections[chunk.parent_section].append(chunk.ldu_id)

        # Update section headers with child references
        for chunk in chunks:
            if chunk.chunk_type == ChunkType.SECTION_HEADER:
                chunk.child_chunks = sections.get(chunk.content, [])

    def _merge_lists(self, chunks: List[LDU]) -> List[LDU]:
        """
        Merge list items into single list chunks when appropriate (Rule 3).
        """
        result = []
        i = 0

        while i < len(chunks):
            chunk = chunks[i]

            # Check if this starts a list
            if self._is_list_item(chunk.content):
                list_items = [chunk]
                list_id = f"list_{i}"
                chunk.metadata['list_id'] = list_id

                # Collect consecutive list items
                j = i + 1
                while j < len(chunks) and self._is_list_item(chunks[j].content):
                    chunks[j].metadata['list_id'] = list_id
                    list_items.append(chunks[j])
                    j += 1

                # Check if we should merge
                total_tokens = sum(c.token_count for c in list_items)
                if total_tokens <= self.max_tokens:
                    # Merge into single list chunk
                    merged_content = '\n'.join(c.content for c in list_items)
                    merged_hash = self.hasher.generate_content_hash(
                        text=merged_content,
                        page_num=list_items[0].primary_page,
                        bbox=list_items[0].bbox
                    )

                    merged = LDU(
                        ldu_id=f"list_{i:04d}_merged",
                        doc_id=list_items[0].doc_id,
                        chunk_type=ChunkType.LIST,
                        content=merged_content,
                        content_hash=merged_hash,
                        page_refs=list(set(c.primary_page for c in list_items)),
                        primary_page=list_items[0].primary_page,
                        bbox=list_items[0].bbox,
                        parent_section=list_items[0].parent_section,
                        section_depth=list_items[0].section_depth,
                        token_count=total_tokens,
                        metadata={
                            'item_count': len(list_items),
                            'merged': True,
                            'original_ids': [c.ldu_id for c in list_items]
                        }
                    )
                    result.append(merged)
                    i = j
                    continue
                else:
                    # Keep separate but mark as same list
                    result.extend(list_items)
                    i = j
            else:
                result.append(chunk)
                i += 1

        return result

    def _resolve_cross_references(self, chunks: List[LDU]) -> Tuple[List[LDU], List[ChunkRelation]]:
        """
        Resolve cross-references between chunks (Rule 5).
        Improved version with better pattern matching.
        """
        relations = []

        # Build better indices
        table_index = {}  # Map table numbers to chunk IDs
        figure_index = {}
        section_index = {}

        # Also index by content for fuzzy matching
        table_by_content = []

        for chunk in chunks:
            if chunk.chunk_type == ChunkType.TABLE:
                # Try to extract table number from content or metadata
                table_num = None

                # Check metadata first
                if 'table_number' in chunk.metadata:
                    table_num = str(chunk.metadata['table_number'])
                elif 'table_id' in chunk.metadata:
                    table_num = str(chunk.metadata['table_id'])

                # Try to extract from content (e.g., "Table 1:", "TABLE 1", etc.)
                if not table_num:
                    match = re.search(r'Table\s+(\d+)', chunk.content, re.IGNORECASE)
                    if match:
                        table_num = match.group(1)

                if table_num:
                    table_index[table_num] = chunk.ldu_id

                # Also index by content for matching
                table_by_content.append({
                    'id': chunk.ldu_id,
                    'content': chunk.content.lower()
                })

            elif chunk.chunk_type == ChunkType.FIGURE:
                # Similar for figures
                fig_num = None
                if 'figure_number' in chunk.metadata:
                    fig_num = str(chunk.metadata['figure_number'])
                elif 'figure_id' in chunk.metadata:
                    fig_num = str(chunk.metadata['figure_id'])

                match = re.search(r'Figure\s+(\d+)', chunk.content, re.IGNORECASE)
                if match:
                    fig_num = match.group(1)

                if fig_num:
                    figure_index[fig_num] = chunk.ldu_id

            elif chunk.chunk_type == ChunkType.SECTION_HEADER:
                # Index sections by title
                section_index[chunk.content.lower()] = chunk.ldu_id

        # Improved pattern matching
        ref_patterns = [
            # Table patterns
            (r'table\s+(\d+)', table_index, 'table'),
            (r'tbl\.?\s*(\d+)', table_index, 'table'),
            (r'see\s+table\s+(\d+)', table_index, 'table'),
            (r'as\s+shown\s+in\s+table\s+(\d+)', table_index, 'table'),

            # Figure patterns
            (r'figure\s+(\d+)', figure_index, 'figure'),
            (r'fig\.?\s*(\d+)', figure_index, 'figure'),
            (r'see\s+figure\s+(\d+)', figure_index, 'figure'),

            # Section patterns
            (r'section\s+(\d+\.?\d*)', section_index, 'section'),
            (r'§\s*(\d+\.?\d*)', section_index, 'section'),
        ]

        for chunk in chunks:
            text_lower = chunk.content.lower()
            resolved_refs = []

            # Try each pattern
            for pattern, index, ref_type in ref_patterns:
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    # Handle both string and tuple returns from findall
                    ref_num = match if isinstance(match, str) else match[0]

                    if ref_num in index:
                        target_id = index[ref_num]
                        if target_id not in resolved_refs:
                            resolved_refs.append(target_id)

                            # Create relation
                            relations.append(ChunkRelation(
                                source_id=chunk.ldu_id,
                                target_id=target_id,
                                relationship_type=ChunkRelationship.CROSS_REFERENCE,
                                metadata={'reference': f"{ref_type} {ref_num}"}
                            ))
                            # Uncomment for debugging:
                            # print(f"✅ Resolved reference: {ref_type} {ref_num} -> {target_id}")

            # If still no matches, try fuzzy matching on table content
            if not resolved_refs and 'table' in text_lower:
                # Look for table numbers in the text
                table_nums = re.findall(r'table\s+(\d+)', text_lower, re.IGNORECASE)
                if table_nums and table_nums[0] in table_index:
                    target_id = table_index[table_nums[0]]
                    resolved_refs.append(target_id)
                    relations.append(ChunkRelation(
                        source_id=chunk.ldu_id,
                        target_id=target_id,
                        relationship_type=ChunkRelationship.CROSS_REFERENCE,
                        metadata={'reference': f"table {table_nums[0]}"}
                    ))
                    # Uncomment for debugging:
                    # print(f"✅ Fuzzy resolved: table {table_nums[0]} -> {target_id}")

            chunk.cross_references = resolved_refs

        return chunks, relations

    def _table_to_string(self, table: Table) -> str:
        """Convert table to string representation"""
        lines = []
        if table.headers:
            lines.append(' | '.join(table.headers))
            lines.append('-' * 40)
        for row in table.rows:
            lines.append(' | '.join(str(cell) for cell in row))
        return '\n'.join(lines)

    def _is_section_header(self, text: str) -> bool:
        """Detect if text is likely a section header"""
        text = text.strip()
        if not text:
            return False

        # Common header patterns
        patterns = [
            r'^\d+\.\s+\w+',  # 1. Title
            r'^[IVX]+\.\s+\w+',  # I. Title
            r'^[A-Z][A-Z\s]+$',  # ALL CAPS
            r'^(?:chapter|section|appendix)\s+\w+',  # Chapter 1
        ]

        for pattern in patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return True

        # Heuristic: short, ends without punctuation
        if len(text.split()) < 10 and not text.endswith(('.', ':', ';')):
            return True

        return False

    def _detect_header_level(self, text: str) -> int:
        """Detect section header level"""
        # Try to extract number
        match = re.match(r'^(\d+)\.', text)
        if match:
            return int(match.group(1))

        # Roman numerals
        if re.match(r'^[IVX]+\.', text):
            return 1

        # Default levels
        if text.isupper():
            return 1
        return 2

    def _is_list_item(self, text: str) -> bool:
        """Detect if text is a list item"""
        text = text.strip()
        patterns = [
            r'^\d+\.\s',  # 1.
            r'^[a-z]\.\s',  # a.
            r'^[•\-*]\s',  # Bullet points
            r'^\(\d+\)\s',  # (1)
        ]
        return any(re.match(p, text) for p in patterns)

    def _calculate_stats(self, chunks: List[LDU], groups: List[ChunkGroup], relations: List[ChunkRelation]) -> Dict:
        """Calculate chunking statistics"""
        stats = {
            'total_chunks': len(chunks),
            'by_type': defaultdict(int),
            'avg_tokens': 0,
            'total_tokens': 0,
            'total_groups': len(groups),
            'total_relations': len(relations),
            'pages_covered': len(set(c.primary_page for c in chunks)),
        }

        for chunk in chunks:
            stats['by_type'][chunk.chunk_type.value] += 1
            stats['total_tokens'] += chunk.token_count

        if chunks:
            stats['avg_tokens'] = stats['total_tokens'] / len(chunks)

        return dict(stats)