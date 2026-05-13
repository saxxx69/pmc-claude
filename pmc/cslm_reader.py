"""
cslm_reader.py — API per leggere nodi CSLM dal grafo PMC.
Opposto di cslm_writer.py — query layer thread-safe per la cognitive state navigation.
"""
from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Any


class CSLMReader:
    """
    Legge nodi e proprietà CSLM dal database PMC.
    Thread-safe: ogni query apre/chiude la connessione.
    """

    def __init__(self, db_path: str):
        self.db = db_path

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db, timeout=10)
        con.row_factory = sqlite3.Row  # accesso colonnecome dict
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def get_recent_events(self, limit: int = 50, node_type: Optional[str] = None) -> list[dict]:
        """
        Ritorna i nodi CSLM recenti, ordinati per created_at DESC.
        Se node_type è specificato (es. 'EVENT_LOG', 'INTERRUPT_L1'), filtra per tipo.
        """
        try:
            with self._conn() as con:
                if node_type:
                    query = """
                        SELECT id, type_id, label, properties, confidence, created_at
                        FROM nodes
                        WHERE type_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """
                    rows = con.execute(query, (node_type, limit)).fetchall()
                else:
                    query = """
                        SELECT id, type_id, label, properties, confidence, created_at
                        FROM nodes
                        ORDER BY created_at DESC
                        LIMIT ?
                    """
                    rows = con.execute(query, (limit,)).fetchall()

                events = []
                for row in rows:
                    try:
                        props = json.loads(row['properties']) if row['properties'] else {}
                    except json.JSONDecodeError:
                        props = {}

                    events.append({
                        'id': row['id'],
                        'type': row['type_id'],
                        'label': row['label'],
                        'properties': props,
                        'confidence': row['confidence'],
                        'created_at': row['created_at'],
                    })
                return events
        except Exception as e:
            return [{'error': f'CSLMReader.get_recent_events failed: {str(e)}'}]

    def get_active_interrupts(self, min_salience: float = 0.5) -> list[dict]:
        """
        Ritorna interrupt L1/L2/L3 non risolti.
        min_salience è usato per filtrare L2 (L1/L3 non hanno salience_score).
        """
        try:
            with self._conn() as con:
                # L1 e L3: seleziona dove resolved=False (nella properties)
                # L2: seleziona dove salience_score >= min_salience
                query = """
                    SELECT id, type_id, label, properties, confidence, created_at
                    FROM nodes
                    WHERE type_id IN ('INTERRUPT_L1', 'INTERRUPT_L2', 'INTERRUPT_L3')
                    ORDER BY created_at DESC
                    LIMIT 100
                """
                rows = con.execute(query).fetchall()

                interrupts = []
                for row in rows:
                    try:
                        props = json.loads(row['properties']) if row['properties'] else {}
                    except json.JSONDecodeError:
                        props = {}

                    # Filtro L1: resolved=False
                    if row['type_id'] == 'INTERRUPT_L1':
                        if props.get('resolved', False):
                            continue

                    # Filtro L2: salience >= min_salience
                    elif row['type_id'] == 'INTERRUPT_L2':
                        if props.get('salience_score', 0.0) < min_salience:
                            continue

                    interrupts.append({
                        'id': row['id'],
                        'type': row['type_id'],
                        'label': row['label'],
                        'trigger_metric': props.get('trigger_metric'),
                        'trigger_value': props.get('trigger_value'),
                        'threshold': props.get('threshold'),
                        'pattern': props.get('pattern'),
                        'salience_score': props.get('salience_score'),
                        'action': props.get('action'),
                        'resolved': props.get('resolved', False),
                        'confidence': row['confidence'],
                        'created_at': row['created_at'],
                    })

                return interrupts
        except Exception as e:
            return [{'error': f'CSLMReader.get_active_interrupts failed: {str(e)}'}]

    def get_recent_decisions(self, limit: int = 20) -> list[dict]:
        """
        Ritorna ARBITRATION_OUTCOME recenti — decisioni prese dal layer ECL.
        """
        try:
            with self._conn() as con:
                query = """
                    SELECT id, type_id, label, properties, confidence, created_at
                    FROM nodes
                    WHERE type_id = 'ARBITRATION_OUTCOME'
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                rows = con.execute(query, (limit,)).fetchall()

                decisions = []
                for row in rows:
                    try:
                        props = json.loads(row['properties']) if row['properties'] else {}
                    except json.JSONDecodeError:
                        props = {}

                    decisions.append({
                        'id': row['id'],
                        'type': row['type_id'],
                        'label': row['label'],
                        'outcome': props.get('outcome'),
                        'reason': props.get('reason'),
                        'ecl_confidence': props.get('ecl_confidence'),
                        'confidence': row['confidence'],
                        'created_at': row['created_at'],
                    })

                return decisions
        except Exception as e:
            return [{'error': f'CSLMReader.get_recent_decisions failed: {str(e)}'}]

    def get_pattern_frequency(self, hours: int = 24) -> dict:
        """
        Conta frequenza di pattern INTERRUPT_L2 nelle ultime N ore.
        Ritorna dict {pattern: count} top patterns ordinati per count DESC.
        """
        try:
            with self._conn() as con:
                cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

                query = """
                    SELECT properties
                    FROM nodes
                    WHERE type_id = 'INTERRUPT_L2'
                    AND created_at >= ?
                """
                rows = con.execute(query, (cutoff,)).fetchall()

                pattern_counts = {}
                for row in rows:
                    try:
                        props = json.loads(row['properties']) if row['properties'] else {}
                    except json.JSONDecodeError:
                        continue

                    pattern = props.get('pattern', 'unknown')
                    pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

                # Sort by count desc
                sorted_patterns = dict(sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True))
                return sorted_patterns
        except Exception as e:
            return {'error': f'CSLMReader.get_pattern_frequency failed: {str(e)}'}

    def get_summary_stats(self) -> dict:
        """
        Ritorna statistiche rapide: totale eventi 24h, interrupt attivi, top pattern.
        """
        try:
            with self._conn() as con:
                cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

                # Conteggio event_log ultimi 24h
                events_24h = con.execute(
                    "SELECT COUNT(*) as count FROM nodes WHERE type_id='EVENT_LOG' AND created_at >= ?",
                    (cutoff_24h,)
                ).fetchone()['count']

                # Conteggio interrupt non risolti
                query_interrupts = """
                    SELECT COUNT(*) as count FROM nodes
                    WHERE type_id IN ('INTERRUPT_L1', 'INTERRUPT_L2', 'INTERRUPT_L3')
                """
                active_interrupts = con.execute(query_interrupts).fetchone()['count']

                # Top pattern (ultime 24h)
                patterns = self.get_pattern_frequency(hours=24)
                top_pattern = list(patterns.items())[0] if patterns else ('none', 0)

                return {
                    'total_events_24h': events_24h,
                    'active_interrupts': active_interrupts,
                    'top_pattern': top_pattern[0],
                    'top_pattern_count': top_pattern[1],
                }
        except Exception as e:
            return {'error': f'CSLMReader.get_summary_stats failed: {str(e)}'}
