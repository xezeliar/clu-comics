"""Dashboard Series shelf: series list, per-series issue carousel, issue info.

Read-only except ``DELETE /api/dashboard/issue-read`` (Mark Unread). None of
these routes clears the "new" badge (``mark_series_visited``): only opening the
folder does that.
"""
import os
import re
from datetime import date

from flask import Blueprint, jsonify, request, url_for

from core import folder_art
from core.app_logging import app_logger
from core.auth import current_user, enforce_path_access, filter_paths_for_user
from core.comicinfo import read_comicinfo_from_zip
from core.database import (
    current_user_id, db_conn, delete_reading_position,
    get_issues_for_series, get_new_arrival_counts, get_wanted_marks, unmark_issue_read,
)
from helpers.collection import issue_match_key
from helpers.library import is_valid_library_path

series_shelf_bp = Blueprint('series_shelf', __name__)

_COMIC = "f.type = 'file' AND (f.name LIKE '%.cbz' OR f.name LIKE '%.cbr')"
_CREDITS = {
    'writer': 'Writer', 'penciller': 'Penciller', 'inker': 'Inker',
    'colorist': 'Colorist', 'letterer': 'Letterer',
    'cover_artist': 'CoverArtist', 'editor': 'Editor',
}


def _sort_key(number):
    m = re.match(r'\s*(-?\d+(?:\.\d+)?)', str(number or ''))
    return (0, float(m.group(1)), str(number)) if m else (1, 0.0, str(number or ''))


@series_shelf_bp.route('/api/dashboard/series')
def dashboard_series():
    try:
        offset = max(int(request.args.get('offset', 0)), 0)
        limit = min(max(int(request.args.get('limit', 30)), 1), 100)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid paging'}), 400

    with db_conn() as conn:
        if not conn:
            return jsonify({'success': False, 'error': 'Database unavailable'}), 500
        rows = [dict(r) for r in conn.execute(
            "SELECT s.id, s.name, s.volume, s.mapped_path, s.issue_count, "
            "(SELECT MAX(f.first_indexed_at) FROM file_index f "
            f" WHERE f.parent = s.mapped_path AND {_COMIC}) AS newest "
            "FROM series s WHERE s.mapped_path IS NOT NULL AND s.mapped_path != '' "
            "ORDER BY newest IS NULL, newest DESC, s.name COLLATE NOCASE, s.id")]
    rows = filter_paths_for_user(current_user(), rows, key='mapped_path')
    page = rows[offset:offset + limit]
    folders = [r['mapped_path'] for r in page]

    owned, first_issue = {}, {}
    if folders:
        marks = ",".join("?" * len(folders))
        with db_conn() as conn:
            for parent, n, first in conn.execute(
                    f"SELECT f.parent, COUNT(*), MIN(f.path) FROM file_index f "
                    f"WHERE {_COMIC} AND f.parent IN ({marks}) GROUP BY f.parent",
                    folders):
                owned[parent] = n
                first_issue[parent] = first  # cover fallback: first issue by path
    art = folder_art.get_art_batch(folders)
    new_counts = get_new_arrival_counts(folders)

    series = []
    for r in page:
        folder = r['mapped_path']
        cover = (folder_art.art_url(folder, 'folder', record=art[folder])
                 if folder in art else None)
        if not cover and folder in first_issue:
            cover = url_for('get_thumbnail', path=first_issue[folder])
        series.append({
            'id': r['id'], 'name': r['name'], 'volume': r['volume'],
            'folder': folder,
            'folder_url': url_for('collection.collection', path=folder),
            'cover_url': cover,
            'owned': owned.get(folder, 0),
            'total': r['issue_count'],
            'new_count': new_counts.get(folder, 0),
        })
    return jsonify({'success': True, 'total': len(rows), 'series': series})


@series_shelf_bp.route('/api/dashboard/series/<int:series_id>/issues')
def dashboard_series_issues(series_id):
    with db_conn() as conn:
        if not conn:
            return jsonify({'success': False, 'error': 'Database unavailable'}), 500
        s = conn.execute(
            "SELECT id, name, mapped_path, monitored FROM series WHERE id = ?",
            (series_id,)).fetchone()
        if not s or not s['mapped_path']:
            return jsonify({'success': False, 'error': 'Series not found'}), 404
        folder = s['mapped_path']
        if not filter_paths_for_user(current_user(), [{'p': folder}], key='p'):
            return jsonify({'success': False, 'error': 'Series not found'}), 404
        files = [dict(r) for r in conn.execute(
            f"SELECT f.path, f.ci_number, f.ci_title FROM file_index f "
            f"WHERE {_COMIC} AND f.parent = ?", (folder,))]
        paths = [f['path'] for f in files]
        uid, read, progress = current_user_id(), set(), {}
        for i in range(0, len(paths), 500):
            chunk = paths[i:i + 500]
            marks = ",".join("?" * len(chunk))
            read.update(r[0] for r in conn.execute(
                f"SELECT issue_path FROM issues_read WHERE user_id = ? "
                f"AND issue_path IN ({marks})", [uid] + chunk))
            for r in conn.execute(
                    f"SELECT comic_path, page_number, total_pages FROM reading_positions "
                    f"WHERE user_id = ? AND comic_path IN ({marks})", [uid] + chunk):
                progress[r[0]] = (r[1], r[2])

    issues, have = [], set()
    for f in files:
        num = f['ci_number'] if f['ci_number'] is not None else ''
        have.add(issue_match_key(num))
        item = {
            'number': str(num), 'owned': True, 'path': f['path'],
            'title': f['ci_title'] or None, 'date': None,
            'thumb_url': url_for('get_thumbnail', path=f['path']),
            'read': f['path'] in read,
        }
        if f['path'] in progress:
            item['page'], item['total_pages'] = progress[f['path']]
        issues.append(item)
    # Missing = released issues of the series that no file covers. The Wanted
    # cache skips Not-monitored series, so read the issues table instead.
    monitored = bool(s['monitored'])
    marks = set() if monitored else {issue_match_key(n) for n in get_wanted_marks(series_id)}
    today = date.today().isoformat()
    for w in get_issues_for_series(series_id):
        when = w['store_date'] or w['cover_date']
        if issue_match_key(w['number']) in have or (when and when > today):
            continue
        issues.append({
            'number': str(w['number'] or ''), 'owned': False,
            'title': w['name'] or None, 'date': when or None, 'read': False,
            'wanted': monitored or issue_match_key(w['number']) in marks,
        })
    issues.sort(key=lambda i: _sort_key(i['number']))
    return jsonify({
        'success': True,
        'series': {'id': s['id'], 'name': s['name'], 'monitored': bool(s['monitored'])},
        'issues': issues,
    })


@series_shelf_bp.route('/api/dashboard/issue-info')
def dashboard_issue_info():
    path = request.args.get('path') or ''
    if not path or not is_valid_library_path(path):
        return jsonify({'success': False, 'error': 'Invalid path'}), 400
    denied = enforce_path_access(path)
    if denied:
        return denied
    if not os.path.isfile(path):
        return jsonify({'success': False, 'error': 'Not found'}), 404

    info = {}
    if path.lower().endswith('.cbz'):
        try:
            info = read_comicinfo_from_zip(path)
        except Exception as e:
            app_logger.warning(f"issue-info: cannot read ComicInfo from {path}: {e}")
    date = '-'.join(info[k] for k in ('Year', 'Month', 'Day') if info.get(k))
    return jsonify({
        'success': True,
        'title': info.get('Title') or '',
        'summary': info.get('Summary') or '',
        'date': date,
        'credits': {k: info.get(v) or '' for k, v in _CREDITS.items()},
    })


@series_shelf_bp.route('/api/dashboard/issue-read', methods=['DELETE'])
def dashboard_issue_unread():
    """Mark Unread: drop the read mark and the bookmark for this user."""
    path = request.args.get('path') or ''
    if not path:
        return jsonify({'success': False, 'error': 'Missing path'}), 400
    denied = enforce_path_access(path)
    if denied:
        return denied
    ok = unmark_issue_read(path) and delete_reading_position(path)
    return jsonify({'success': bool(ok)})
