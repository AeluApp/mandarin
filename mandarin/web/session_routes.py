"""WebSocket session routes — full and mini drill sessions."""

import json
import logging
import threading

from flask import request
from flask_login import current_user
from flask_sock import Sock
from simple_websocket import ConnectionClosed

import random

from .. import db
from ..tier_gate import check_session_limit
from ..scheduler import plan_standard_session, plan_minimal_session
from ..runner import run_session
from .bridge import WebBridge
from .session_store import session_store, RESUME_TIMEOUT
from .middleware import _sanitize_error

logger = logging.getLogger(__name__)


def _detect_client_platform():
    """Detect client platform from User-Agent and request params."""
    ua = (request.headers.get("User-Agent") or "").lower()
    if request.args.get("native") == "1" or "capacitor" in ua:
        # Distinguish iOS vs Android
        if "iphone" in ua or "ipad" in ua or "ios" in ua:
            return "ios"
        elif "android" in ua:
            return "android"
        return "ios"  # Capacitor default is iOS for Aelu
    if "tauri" in ua or "__TAURI__" in (request.headers.get("Referer") or ""):
        return "macos"
    # Check if from localhost (dev) vs production domain
    host = request.host or ""
    if "localhost" in host or "127.0.0.1" in host:
        return "web_local"
    return "web"

# ── Per-user session locking ──────────────────────────────────

_user_locks = {}   # int -> threading.Lock
_user_threads = {}  # int -> threading.Thread or None
_lock_mutex = threading.Lock()


def _get_user_lock(user_id: int):
    with _lock_mutex:
        if user_id not in _user_locks:
            _user_locks[user_id] = threading.Lock()
        return _user_locks[user_id], _user_threads.get(user_id)


def _set_user_thread(user_id: int, thread):
    with _lock_mutex:
        if thread is None:
            _user_locks.pop(user_id, None)
            _user_threads.pop(user_id, None)
        else:
            _user_threads[user_id] = thread


# ── WS listen loop ───────────────────────────────────────────

def _ws_listen_loop(ws, bridge, session_thread, *, close_on_disconnect=True):
    """Receive answers from the browser until the session thread ends."""
    while session_thread.is_alive():
        try:
            raw = ws.receive(timeout=1)
            if raw is None:
                if not session_thread.is_alive():
                    break
                continue
            data = json.loads(raw)
            if data.get("type") == "answer":
                logger.debug("[%s] answer received: %r", bridge.session_uuid, data.get("value", ""))
                bridge.receive_answer(data.get("value", ""))
            elif data.get("type") == "word_lookup":
                hanzi = data.get("hanzi", "")
                if hanzi:
                    bridge.receive_word_lookup(hanzi)
                    logger.debug("[%s] word_lookup: %s", bridge.session_uuid, hanzi)
            elif data.get("type") == "audio_data":
                logger.debug("[%s] audio data received (%s bytes, transcript=%s)",
                           bridge.session_uuid,
                           len(data.get("data", "") or "") if data.get("data") else "null",
                           repr(data.get("transcript", "")[:30]) if data.get("transcript") else "null")
                bridge.receive_audio_data(data.get("data"), data.get("transcript"))
        except ConnectionClosed:
            logger.info("[%s] connection closed by client", bridge.session_uuid)
            if close_on_disconnect:
                bridge.close()
            else:
                bridge.disconnect()
            return
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    logger.debug("[%s] listen loop ended (thread dead)", bridge.session_uuid)


# ── Shared WS session handler ────────────────────────────────

def _handle_ws_session(ws, planner_fn, label):
    """Shared WebSocket session handler for both full and mini sessions."""
    if not current_user.is_authenticated:
        try:
            ws.send(json.dumps({"type": "error", "message": "Authentication required"}))
            ws.close()
        except (ConnectionClosed, OSError):
            pass
        return

    user_id = current_user.id
    user_lock, _ = _get_user_lock(user_id)

    try:
        first_raw = ws.receive(timeout=0.5)
    except (ConnectionClosed, TimeoutError, OSError):
        first_raw = None
    first_data = {}
    if first_raw:
        try:
            first_data = json.loads(first_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    # ── Resume path ──────────────────────────────────────
    if first_data.get("type") == "resume" and first_data.get("resume_token"):
        token = first_data.get("resume_token")
        active = session_store.claim_for_resume(token, user_id)
        if active:
            logger.info("[%s] resuming %s via token %s", active.bridge.session_uuid, label, token)
            try:
                active.bridge.swap_ws(ws)
                session_store.release_claim(token)
                active.bridge._send({"type": "session_init", "resume_token": token, "resumed": True})
                _ws_listen_loop(ws, active.bridge, active.session_thread, close_on_disconnect=False)
                if active.session_thread.is_alive():
                    active.bridge.disconnect()
            except (ConnectionClosed, OSError, ConnectionError) as e:
                logger.exception("%s resume path error for token %s: %s", label, token, e)
                session_store.release_claim(token)
            finally:
                if not active.session_thread.is_alive():
                    session_store.remove(token)
                    _set_user_thread(user_id, None)
                    try:
                        user_lock.release()
                    except RuntimeError:
                        pass
            return
        else:
            logger.info("resume token %s not found or session dead, starting new %s", token, label)
            session_store.remove(token)

    # ── Tier gate: check session limit ────────────────────
    try:
        with db.connection() as gate_conn:
            if not check_session_limit(gate_conn, user_id):
                bridge = WebBridge(ws)
                bridge.send_error("You\u2019ve used today\u2019s sessions. Tomorrow brings a fresh set, or upgrade anytime for unlimited.")
                return
    except Exception as e:
        logger.warning("Tier gate check failed (allowing): %s", e)

    # ── New session path ─────────────────────────────────
    if not user_lock.acquire(blocking=False):
        _, stale_thread = _get_user_lock(user_id)
        released = False

        # Case 1: thread is dead — stale lock
        if stale_thread is not None and not stale_thread.is_alive():
            logger.warning("%s user %d: stale lock (thread dead), force-releasing", label, user_id)
            session_store.cleanup_expired()
            try:
                user_lock.release()
                released = True
            except RuntimeError:
                pass

        # Case 2: thread alive but bridge disconnected — orphaned session
        if not released and stale_thread is not None and stale_thread.is_alive():
            orphan = session_store.find_by_user(user_id)
            if orphan and (orphan.bridge._closed or orphan.bridge._disconnected):
                logger.warning("%s user %d: orphaned session (bridge closed), force-closing", label, user_id)
                orphan.bridge.close()
                stale_thread.join(timeout=5)
                session_store.cleanup_expired()
                try:
                    user_lock.release()
                    released = True
                except RuntimeError:
                    pass

        if released:
            if not user_lock.acquire(blocking=False):
                logger.warning("%s rejected for user %d: lock still held after force-release", label, user_id)
                bridge = WebBridge(ws)
                bridge.send_error("A session is already in progress. It should reconnect automatically \u2014 if not, refresh the page.")
                return
        else:
            logger.warning("%s rejected for user %d: session already active", label, user_id)
            bridge = WebBridge(ws)
            bridge.send_error("A session is already in progress. It should reconnect automatically \u2014 if not, refresh the page.")
            return
    bridge = WebBridge(ws)
    has_mic = request.args.get('mic', '1') != '0'
    client_platform = _detect_client_platform()  # capture in request context before thread
    resume_token = bridge.session_uuid
    logger.info("[%s] %s WS connected user=%d (mic=%s)", bridge.session_uuid, label, user_id, has_mic,
                extra={"user_id": user_id})
    bridge._send({"type": "session_init", "resume_token": resume_token})

    def _show_reading_opener(conn, show_fn, input_fn, user_id):
        """Show a scaffolded reading passage after drills.

        Unknown words get pinyin/english annotations so the passage
        feels supportive rather than confrontational.
        """
        try:
            from ..media import load_reading_passages
            # Determine user's effective HSK level
            mastery = db.get_mastery_by_hsk(conn, user_id=user_id)
            user_hsk = 1
            if mastery:
                active = [k for k, v in mastery.items() if v.get("seen", 0) > 0]
                user_hsk = max(active) if active else 1

            passages = load_reading_passages(user_hsk)
            if not passages:
                passages = load_reading_passages(1)  # Fallback to HSK 1
            if not passages:
                return

            passage = random.choice(passages)
            text = passage.get("text_zh", "")
            if not text:
                return

            # Truncate long passages for the opener (max ~120 chars)
            if len(text) > 120:
                cut = text[:120].rfind("。")
                if cut > 30:
                    text = text[:cut + 1]
                else:
                    text = text[:120] + "…"

            # Build per-character scaffolding: look up which chars the
            # user knows vs doesn't, and provide pinyin+english for unknown ones.
            import re
            cjk_chars = list(set(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text)))
            char_scaffold = {}
            if cjk_chars:
                placeholders = ",".join("?" for _ in cjk_chars)
                # Check which characters the user has seen/mastered
                known_rows = conn.execute(f"""
                    SELECT ci.hanzi, p.mastery_stage, ci.pinyin, ci.english
                    FROM progress p
                    JOIN content_item ci ON p.content_item_id = ci.id
                    WHERE p.user_id = ?
                      AND ci.hanzi IN ({placeholders})
                      AND p.times_correct > 0
                """, [user_id] + cjk_chars).fetchall()
                known_chars = {r["hanzi"] for r in known_rows}

                # For unknown chars, look up pinyin + english from content_item
                unknown = [c for c in cjk_chars if c not in known_chars]
                if unknown:
                    unk_placeholders = ",".join("?" for _ in unknown)
                    lookup_rows = conn.execute(f"""
                        SELECT hanzi, pinyin, english
                        FROM content_item
                        WHERE hanzi IN ({unk_placeholders})
                        LIMIT 100
                    """, unknown).fetchall()
                    for r in lookup_rows:
                        char_scaffold[r["hanzi"]] = {
                            "pinyin": r["pinyin"] or "",
                            "english": r["english"] or "",
                            "known": False,
                        }

                # Mark known chars (no scaffold needed, but include for context)
                for r in known_rows:
                    if r["hanzi"] not in char_scaffold:
                        char_scaffold[r["hanzi"]] = {
                            "pinyin": r["pinyin"] or "",
                            "english": r["english"] or "",
                            "known": True,
                        }

            bridge._send({
                "type": "reading_opener",
                "title": passage.get("title_zh", passage.get("title", "")),
                "text_zh": text,
                "passage_id": passage.get("id", ""),
                "hsk_level": passage.get("hsk_level", 1),
                "scaffold": char_scaffold,
                "position": "post_drills",
            })
            # Wait for user to dismiss the reading opener
            bridge.input_fn("")
        except Exception as e:
            logger.warning("reading opener skipped: %s", e, exc_info=True)

    def _run_reading_block(bridge, block, conn, user_id):
        """Run a reading block in exposure or re-read mode.

        Exposure mode (is_reread=False):
          - Show passage with tap-to-gloss, collect word_lookup events
          - Comprehension questions only if passage has them AND user spent >60s
          - Returns list of looked-up hanzi

        Re-read mode (is_reread=True):
          - Show same passage with drilled words highlighted
          - No questions, just "Continue" to advance
          - Returns empty list
        """
        import time as _time

        if block.is_reread:
            # ── Re-read mode: show passage with drilled words highlighted ──
            bridge._send({
                "type": "reading_block",
                "mode": "reread",
                "passage": block.passage,
                "drilled_words": block.looked_up_words,
                "questions": [],
                "question_count": 0,
            })
            # Wait for user to click "Continue"
            bridge.input_fn("")
            return []

        # ── Exposure mode: user reads at their own pace, taps unknowns ──
        # Build per-character scaffold (same as reading opener)
        import re as _re
        text = block.passage.get("content_hanzi", "")
        cjk_chars = list(set(_re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]', text)))
        scaffold = {}
        if cjk_chars:
            placeholders = ",".join("?" for _ in cjk_chars)
            try:
                known_rows = conn.execute(f"""
                    SELECT ci.hanzi, ci.pinyin, ci.english
                    FROM progress p
                    JOIN content_item ci ON p.content_item_id = ci.id
                    WHERE p.user_id = ?
                      AND ci.hanzi IN ({placeholders})
                      AND p.times_correct > 0
                """, [user_id] + cjk_chars).fetchall()
                known_set = {r["hanzi"] for r in known_rows}

                # Unknown chars: look up pinyin + english
                unknown = [c for c in cjk_chars if c not in known_set]
                if unknown:
                    unk_ph = ",".join("?" for _ in unknown)
                    lookup_rows = conn.execute(f"""
                        SELECT hanzi, pinyin, english
                        FROM content_item
                        WHERE hanzi IN ({unk_ph})
                        LIMIT 100
                    """, unknown).fetchall()
                    for r in lookup_rows:
                        scaffold[r["hanzi"]] = {
                            "pinyin": r["pinyin"] or "",
                            "english": r["english"] or "",
                            "known": False,
                        }

                for r in known_rows:
                    if r["hanzi"] not in scaffold:
                        scaffold[r["hanzi"]] = {
                            "pinyin": r["pinyin"] or "",
                            "english": r["english"] or "",
                            "known": True,
                        }
            except Exception:
                pass

        # Clear any stale lookups before exposure begins
        bridge.drain_word_lookups()

        read_start = _time.monotonic()
        bridge._send({
            "type": "reading_block",
            "mode": "exposure",
            "passage": block.passage,
            "scaffold": scaffold,
            "questions": block.questions,
            "question_count": len(block.questions),
        })

        # Wait for user to signal "Done reading"
        bridge.input_fn("")
        read_elapsed = _time.monotonic() - read_start

        # Drain the looked-up words accumulated during reading
        looked_up = bridge.drain_word_lookups()

        # Comprehension questions: only if available AND user spent enough time
        results = []
        if block.questions and read_elapsed > 60:
            for i, q in enumerate(block.questions):
                bridge._send({
                    "type": "reading_question",
                    "index": i,
                    "total": len(block.questions),
                    "question": q.get("question", ""),
                    "options": q.get("options", []),
                })
                answer_raw = bridge.input_fn("")
                try:
                    answer_idx = int(answer_raw)
                except (ValueError, TypeError):
                    answer_idx = -1
                correct = answer_idx == q.get("correct_index", -1)
                results.append(correct)
                bridge._send({
                    "type": "reading_feedback",
                    "index": i,
                    "correct": correct,
                    "explanation": q.get("explanation", ""),
                    "correct_answer": q.get("options", [""])[q.get("correct_index", 0)]
                        if q.get("options") else "",
                })

        # Log to reading_progress
        try:
            conn.execute("""
                INSERT INTO reading_progress
                (user_id, passage_id, completed_at, questions_correct, questions_total,
                 reading_time_seconds, words_looked_up)
                VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
            """, (user_id, block.passage_id, sum(results), len(results),
                  int(read_elapsed), len(looked_up)))
            conn.commit()
        except Exception:
            pass

        # Send block summary
        bridge._send({
            "type": "reading_summary",
            "words_looked_up": len(looked_up),
            "reading_seconds": int(read_elapsed),
            "correct": sum(results),
            "total": len(results),
            "passage_title": block.passage.get("title", ""),
        })

        return looked_up

    def _create_drills_for_words(conn, user_id, hanzi_list):
        """Create quick reinforcement drills for words looked up during reading.

        Returns a list of DrillItems using simple recognition drill types
        (mc, reverse_mc) — these are cleanup drills, not full variety.
        """
        from ..scheduler import DrillItem
        drills = []
        if not hanzi_list:
            return drills

        for hanzi in hanzi_list[:5]:  # Cap at 5 cleanup drills
            try:
                row = conn.execute("""
                    SELECT id, hanzi, pinyin, english
                    FROM content_item
                    WHERE hanzi = ? AND pinyin IS NOT NULL AND pinyin != ''
                    LIMIT 1
                """, (hanzi,)).fetchone()
                if not row:
                    continue

                # Alternate between mc and reverse_mc for variety
                drill_type = "mc" if len(drills) % 2 == 0 else "reverse_mc"
                drills.append(DrillItem(
                    content_item_id=row["id"],
                    hanzi=row["hanzi"],
                    pinyin=row["pinyin"],
                    english=row["english"],
                    modality="reading",
                    drill_type=drill_type,
                    metadata={"source": "reading_cleanup"},
                ))
            except Exception:
                continue

        return drills

    def _run_conversation_block(bridge, block, conn, user_id):
        """Run a conversation scenario with multi-turn dialogue as a session block."""
        scenario = block.scenario

        # Send scenario opening
        bridge._send({
            "type": "conversation_block",
            "scenario_title": scenario.get("title", scenario.get("title_zh", "")),
            "situation": scenario.get("situation", ""),
            "prompt_zh": scenario.get("prompt_zh", scenario.get("prompt", {}).get("zh", "")),
            "prompt_pinyin": scenario.get("prompt_pinyin", scenario.get("prompt", {}).get("pinyin", "")),
            "prompt_en": scenario.get("prompt_en", scenario.get("prompt", {}).get("en", "")),
            "max_turns": block.max_turns,
        })

        # Multi-turn conversation loop
        scores = []
        for turn in range(block.max_turns):
            # Get user response
            user_text = bridge.input_fn("")
            if not user_text or user_text.strip() == "skip":
                break

            # Evaluate response
            try:
                from ..ai.conversation_drill import evaluate_response
                eval_result = evaluate_response(conn, scenario, user_text, turn)
            except Exception:
                eval_result = {"score": 0.5, "feedback": "Unable to evaluate."}

            scores.append(eval_result.get("score", 0.5))

            # Send feedback
            bridge._send({
                "type": "conversation_feedback",
                "turn": turn,
                "score": eval_result.get("score", 0.5),
                "feedback": eval_result.get("feedback", ""),
                "patterns_used": eval_result.get("patterns_used", []),
                "suggestions": eval_result.get("suggestions", []),
            })

            # Generate follow-up if not last turn
            if turn < block.max_turns - 1:
                try:
                    from ..ai.conversation_drill import generate_followup
                    followup = generate_followup(conn, scenario, user_text)
                    bridge._send({
                        "type": "conversation_prompt",
                        "turn": turn + 1,
                        "prompt_zh": followup.get("zh", followup.get("text", "")),
                        "prompt_pinyin": followup.get("pinyin", ""),
                        "prompt_en": followup.get("en", ""),
                    })
                except Exception:
                    break  # Can't continue without follow-up

        # Send conversation summary
        avg_score = sum(scores) / max(len(scores), 1) if scores else 0
        bridge._send({
            "type": "conversation_summary",
            "avg_score": round(avg_score, 2),
            "turns_completed": len(scores),
            "max_turns": block.max_turns,
            "scenario_title": scenario.get("title", ""),
        })

    def _run_listening_block(bridge, block, conn, user_id):
        """Run a listening comprehension block as a session block.

        Flow: audio plays -> user clicks "Ready for questions" ->
        MC questions one at a time -> transcript revealed -> summary.
        """
        # Send listening block to browser (audio URL, no transcript)
        bridge._send({
            "type": "listening_block",
            "audio_url": block.audio_url,
            "question_count": len(block.questions),
            "playback_speed": block.playback_speed,
            "passage_id": block.passage_id,
        })

        # Wait for "listening_done" event (user clicked "Ready for questions")
        bridge.input_fn("")

        # Send questions one at a time
        results = []
        for i, q in enumerate(block.questions):
            bridge._send({
                "type": "listening_question",
                "index": i,
                "total": len(block.questions),
                "question": q.get("question", ""),
                "options": q.get("options", []),
            })
            answer_raw = bridge.input_fn("")
            try:
                answer_idx = int(answer_raw)
            except (ValueError, TypeError):
                answer_idx = -1
            correct = answer_idx == q.get("correct_index", -1)
            results.append(correct)
            bridge._send({
                "type": "listening_feedback",
                "index": i,
                "correct": correct,
                "explanation": q.get("explanation", ""),
                "correct_answer": q.get("options", [""])[q.get("correct_index", 0)]
                    if q.get("options") else "",
            })

        # Reveal transcript with tap-to-gloss data
        bridge._send({
            "type": "listening_transcript",
            "transcript_zh": block.transcript_zh,
            "transcript_pinyin": block.transcript_pinyin,
        })

        # Log to listening_progress
        score = sum(results) / max(len(results), 1) if results else 1.0
        try:
            conn.execute("""
                INSERT INTO listening_progress
                (user_id, passage_id, completed_at, questions_correct, questions_total,
                 comprehension_score, listening_time_seconds, playback_speed, replays)
                VALUES (?, ?, datetime('now'), ?, ?, ?, 0, ?, 0)
            """, (user_id, str(block.passage_id), sum(results), len(results),
                  round(score, 2), block.playback_speed))
            conn.commit()
        except Exception:
            pass

        # Send block summary
        bridge._send({
            "type": "listening_summary",
            "score": round(score, 2),
            "correct": sum(results),
            "total": len(results),
        })

    def _run():
        logger.info("[%s] %s thread started user=%d", bridge.session_uuid, label, user_id)
        from ..audio import set_web_audio_callback, clear_web_audio_callback
        def _on_audio(fname):
            bridge._send({"type": "audio_play", "url": f"/api/audio/{fname}"})
        set_web_audio_callback(_on_audio)

        from ..tone_grading import set_web_recording_callback, clear_web_recording_callback
        def _on_record(duration):
            return bridge.request_recording(duration)
        set_web_recording_callback(_on_record, has_mic=has_mic)

        try:
            with db.connection() as conn:
                plan = planner_fn(conn, user_id=user_id)
                logger.info("[%s] %s planned: %d drills", bridge.session_uuid, label, len(plan.drills))

                # Send focus insights to show adaptive intelligence
                if plan.focus_insights:
                    bridge._send({
                        "type": "focus_insight",
                        "insights": plan.focus_insights,
                        "micro_plan": plan.micro_plan,
                    })

                # Send prerequisite substitution notices
                try:
                    _prereq_sent = set()
                    for drill in plan.drills:
                        meta = drill.metadata or {}
                        if meta.get("prerequisite_substitute"):
                            key = (meta.get("original_grammar", ""),
                                   meta.get("blocking_grammar", ""))
                            if key not in _prereq_sent:
                                _prereq_sent.add(key)
                                bridge._send({
                                    "type": "prerequisite_notice",
                                    "original_grammar": meta["original_grammar"],
                                    "prerequisite_grammar": meta["blocking_grammar"],
                                    "message": (
                                        f"Let\u2019s practice \u2018{meta['blocking_grammar']}\u2019 first "
                                        f"\u2014 it\u2019s needed for \u2018{meta['original_grammar']}\u2019"
                                    ),
                                })
                except Exception:
                    pass  # Prerequisite notices are non-critical

                # ── SDT Autonomy: session focus choice ──
                user_choice = "surprise"
                if label == "session":
                    try:
                        bridge._send({"type": "session_choice", "options": [
                            {"value": "vocabulary", "label": "Vocabulary focus"},
                            {"value": "reading", "label": "Reading focus"},
                            {"value": "listening", "label": "Listening focus"},
                            {"value": "surprise", "label": "Surprise me"},
                        ]})
                        choice_answer = bridge.input_fn("")
                        user_choice = choice_answer.get("value", "surprise") if isinstance(choice_answer, dict) else (str(choice_answer) if choice_answer and str(choice_answer) in ("vocabulary", "reading", "listening", "surprise") else "surprise")
                    except Exception:
                        user_choice = "surprise"

                # ── Metacognitive state for confidence calibration + error reflection ──
                _pending_confidence = [None]  # mutable container for closure
                _drill_index_counter = [0]    # track drill index across callbacks
                _last_drill_item_id = [None]  # item_id of the most recent drill
                _session_id_ref = [None]      # set once run_session creates the session

                def _progress(sid, idx, total, correct, completed, stype):
                    bridge.send_progress(sid, idx, total, correct, completed, stype)
                    _drill_index_counter[0] = completed
                    _session_id_ref[0] = sid
                    # Confidence calibration: prompt after every 5th drill completes
                    if completed > 0 and completed % 5 == 0:
                        try:
                            bridge._send({"type": "confidence_prompt"})
                            conf_answer = bridge.input_fn("")
                            conf_val = conf_answer.get("value", "medium") if isinstance(conf_answer, dict) else str(conf_answer)
                            if conf_val in ("high", "medium", "low"):
                                _pending_confidence[0] = conf_val
                            else:
                                _pending_confidence[0] = "medium"
                        except Exception:
                            _pending_confidence[0] = None

                def _drill_meta(**kwargs):
                    bridge.send_drill_meta(**kwargs)
                    item_id = kwargs.get("content_item_id")
                    is_correct = kwargs.get("correct", False)
                    _last_drill_item_id[0] = item_id

                    # Store pending confidence calibration with this drill's result
                    if _pending_confidence[0] is not None:
                        try:
                            conn.execute(
                                "INSERT INTO confidence_calibration (user_id, session_id, item_id, confidence, was_correct) VALUES (?, ?, ?, ?, ?)",
                                (user_id, str(_session_id_ref[0] or ""), item_id, _pending_confidence[0], 1 if is_correct else 0))
                            conn.commit()
                        except Exception:
                            pass
                        _pending_confidence[0] = None

                    # Error reflection: 30% of wrong answers
                    if not is_correct and random.random() < 0.3:
                        try:
                            bridge._send({"type": "error_reflection"})
                            refl_answer = bridge.input_fn("")
                            refl_type = refl_answer.get("value", "guessed") if isinstance(refl_answer, dict) else str(refl_answer)
                            if refl_type not in ("similar_chars", "tone_confusion", "forgot_meaning", "guessed"):
                                refl_type = "guessed"
                            conn.execute(
                                "INSERT INTO error_reflection (user_id, item_id, reflection_type) VALUES (?, ?, ?)",
                                (user_id, item_id, refl_type))
                            conn.commit()
                        except Exception:
                            pass

                # ── Character decomposition for first-exposure items ──
                # Build a mapping: drill index -> hanzi for new items
                _new_item_hanzi = {}
                for _di, _drill in enumerate(plan.drills):
                    if _drill.is_new and _drill.hanzi:
                        _new_item_hanzi[_di] = _drill.hanzi
                _decomp_drill_idx = [0]  # track which drill the show_fn is rendering

                # Suppress CLI _finalize() text output on web — the structured
                # showComplete() screen handles the summary display via API calls.
                # Detect the ─── divider that starts _finalize output and suppress
                # all subsequent show_fn/input_fn calls.
                _suppressing = [False]

                def _web_show_fn(text, end="\n"):
                    if _suppressing[0]:
                        return
                    # _finalize starts with a 25-char box-drawing divider
                    if "\u2500" * 20 in text:
                        _suppressing[0] = True
                        return

                    # Detect progress indicator [N/M] to track current drill index
                    import re as _re
                    _prog_match = _re.search(r'\[(\d+)/\d+', text)
                    if _prog_match:
                        _decomp_drill_idx[0] = int(_prog_match.group(1)) - 1  # 0-based

                    # Send character decomposition overlay for new items
                    # Trigger on drill label text containing "(new)"
                    if "(new)" in text and _decomp_drill_idx[0] in _new_item_hanzi:
                        try:
                            from ..ai.character_analysis import generate_decomposition_overlay
                            item_hanzi = _new_item_hanzi[_decomp_drill_idx[0]]
                            for char in item_hanzi:
                                overlay = generate_decomposition_overlay(char)
                                if overlay:
                                    bridge._send({
                                        'type': 'character_decomposition',
                                        'character': char,
                                        'radical': overlay.get('radical', ''),
                                        'radical_meaning': overlay.get('radical_meaning', ''),
                                        'phonetic': overlay.get('phonetic', ''),
                                        'phonetic_hint': overlay.get('phonetic_hint', ''),
                                        'family_examples': overlay.get('family_examples', []),
                                    })
                        except Exception:
                            pass  # Decomposition is non-critical

                    bridge.show_fn(text, end)

                def _web_input_fn(prompt):
                    if _suppressing[0]:
                        return ""  # Auto-skip post-session nudges on web
                    return bridge.input_fn(prompt)

                # ── Cleanup loop: exposure reading → drills → re-read ──
                # Run exposure ReadingBlocks BEFORE drills to collect looked-up words
                from ..scheduler import DrillBlock, ReadingBlock, ConversationBlock, ListeningBlock
                looked_up = []
                if label == "session":
                    for block in plan.blocks:
                        if isinstance(block, ReadingBlock) and not block.is_reread and block.passage:
                            try:
                                looked_up = _run_reading_block(bridge, block, conn, user_id)
                            except Exception as e:
                                logger.debug("Exposure reading failed: %s", e)

                    # Inject looked-up words as priority cleanup drills
                    if looked_up:
                        extra_items = _create_drills_for_words(conn, user_id, looked_up)
                        if extra_items:
                            for drill_block in plan.blocks:
                                if isinstance(drill_block, DrillBlock):
                                    drill_block.items = extra_items + drill_block.items
                                    break

                state = run_session(conn, plan, _web_show_fn, _web_input_fn,
                                    user_id=user_id, progress_fn=_progress,
                                    drill_meta_fn=_drill_meta,
                                    client_platform=client_platform)

                # Collect extra summary data for the enriched done message
                done_data = {
                    "items_completed": state.items_completed,
                    "items_correct": state.items_correct,
                    "early_exit": state.early_exit,
                }

                # Error type breakdown from session results
                error_types = {}
                new_count = 0
                for r in state.results:
                    if not r.correct and not r.skipped and r.error_type:
                        error_types[r.error_type] = error_types.get(r.error_type, 0) + 1
                for d in state.plan.drills:
                    if d.is_new:
                        new_count += 1
                if error_types:
                    done_data["error_types"] = error_types
                if new_count > 0:
                    done_data["new_count"] = new_count

                # Response speed from today's progress records
                try:
                    from datetime import date
                    speed_row = conn.execute("""
                        SELECT AVG(p.avg_response_ms) as avg_ms, COUNT(*) as cnt
                        FROM progress p
                        WHERE p.avg_response_ms IS NOT NULL AND p.last_review_date = ?
                          AND p.user_id = ?
                    """, (date.today().isoformat(), user_id)).fetchone()
                    if speed_row and speed_row["avg_ms"] and speed_row["cnt"] >= 3:
                        done_data["speed_avg_s"] = round(speed_row["avg_ms"] / 1000, 1)
                except Exception:
                    pass

                # Streak freeze earning: award a freeze after 7 consecutive days (max 2)
                try:
                    from .middleware import _compute_streak
                    current_streak = _compute_streak(conn, user_id=user_id)
                    if current_streak > 0 and current_streak % 7 == 0:
                        conn.execute("""
                            UPDATE user SET streak_freezes_available = MIN(streak_freezes_available + 1, 2)
                            WHERE id = ? AND streak_freezes_available < 2
                        """, (user_id,))
                        conn.commit()
                except Exception:
                    pass

                # Process post-drill blocks (re-read, conversation, listening)
                if label == "session" and state.items_completed > 0:
                    for block in plan.blocks:
                        if isinstance(block, DrillBlock):
                            continue  # Already processed by run_session
                        if isinstance(block, ReadingBlock) and not block.is_reread:
                            continue  # Already ran before drills
                        try:
                            if isinstance(block, ReadingBlock) and block.is_reread and block.passage:
                                block.looked_up_words = looked_up  # highlight drilled words
                                _run_reading_block(bridge, block, conn, user_id)
                            elif isinstance(block, ConversationBlock) and block.scenario:
                                _run_conversation_block(bridge, block, conn, user_id)
                            elif isinstance(block, ListeningBlock) and block.audio_url:
                                _run_listening_block(bridge, block, conn, user_id)
                        except Exception as e:
                            logger.debug("Block %s failed: %s", block.block_type, e)

                # ── Metacognitive: session self-assessment (Dunlosky 2013) ──
                if state.items_completed > 0:
                    try:
                        bridge._send({"type": "session_assessment"})
                        assess_answer = bridge.input_fn("")
                        rating = assess_answer.get("value", "about_right") if isinstance(assess_answer, dict) else str(assess_answer)
                        if rating not in ("too_easy", "about_right", "too_hard"):
                            rating = "about_right"
                        conn.execute(
                            "INSERT INTO session_self_assessment (user_id, session_id, difficulty_rating) VALUES (?, ?, ?)",
                            (user_id, str(state.session_id), rating))
                        conn.commit()
                    except Exception:
                        pass

                # ── SDT Competence: progress feedback (Ryan & Deci 2000) ──
                try:
                    known_count = conn.execute(
                        "SELECT COUNT(DISTINCT content_item_id) FROM memory_states WHERE user_id = ? AND stability > 1",
                        (user_id,)).fetchone()[0]
                    # Items that were already stable a week ago
                    week_ago_count = conn.execute(
                        "SELECT COUNT(DISTINCT content_item_id) FROM memory_states WHERE user_id = ? AND stability > 1 AND last_reviewed_at <= datetime('now', '-7 days')",
                        (user_id,)).fetchone()[0]
                    gained = known_count - week_ago_count
                    if gained > 0:
                        bridge._send({"type": "competence_feedback", "message": f"You know {known_count} words \u2014 {gained} more than last week."})
                    elif known_count > 0:
                        bridge._send({"type": "competence_feedback", "message": f"You know {known_count} words. Keep going!"})
                except Exception:
                    pass

                # Store user_choice on the session log now that session_id is known
                try:
                    conn.execute("UPDATE session_log SET user_choice = ? WHERE id = ?",
                                 (user_choice, state.session_id))
                    conn.commit()
                except Exception:
                    pass

                bridge.send_done(done_data)
                logger.info("[%s] %s complete: %d/%d", bridge.session_uuid, label, state.items_correct, state.items_completed)
        except Exception as e:
            logger.error("[%s] %s error (%s): %s", bridge.session_uuid, label, type(e).__name__, e)
            bridge.send_error(_sanitize_error(e))
        finally:
            clear_web_audio_callback()
            clear_web_recording_callback()

    try:
        session_thread = threading.Thread(target=_run, daemon=True)
        session_thread.start()
        _set_user_thread(user_id, session_thread)
        session_store.register(resume_token, bridge, session_thread, user_id=user_id)
        _ws_listen_loop(ws, bridge, session_thread, close_on_disconnect=False)
        logger.info("[%s] %s WS handler exiting", bridge.session_uuid, label)
        if session_thread.is_alive():
            bridge.disconnect()
            session_thread.join(timeout=RESUME_TIMEOUT + 5)
        elif not bridge._closed:
            logger.warning("[%s] %s thread died unexpectedly", bridge.session_uuid, label)
            bridge.send_error("Session ended unexpectedly. Please start a new session.")
        session_store.remove(resume_token)
    finally:
        if not session_thread.is_alive():
            bridge.close()
        _set_user_thread(user_id, None)
        try:
            user_lock.release()
        except RuntimeError:
            pass


def register_session_routes(app):
    """Register WebSocket session routes on the Flask app."""
    sock = Sock(app)

    @sock.route("/ws/session")
    def ws_session(ws):
        """WebSocket endpoint — runs a full drill session over the socket."""
        _handle_ws_session(ws, plan_standard_session, "session")

    @sock.route("/ws/mini")
    def ws_mini(ws):
        """WebSocket endpoint — runs a mini session."""
        _handle_ws_session(ws, plan_minimal_session, "mini")
