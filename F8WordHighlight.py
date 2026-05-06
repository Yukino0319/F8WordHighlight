import re
import time

import sublime
import sublime_plugin


PLUGIN_SETTINGS_FILE = "F8WordHighlight.sublime-settings"
REGION_KEY_PREFIX = "f8_word_highlight"
DEFAULT_PALETTE_SCOPES = [
    "region.yellowish",
    "region.greenish",
    "region.bluish",
    "region.orangish",
    "region.purplish",
]


class WordHighlightEntry:
    """保存单个词条的高亮状态 / Store highlight state for one word."""

    def __init__(self, word, region_key, palette_index):
        self.word = word
        self.region_key = region_key
        self.palette_index = palette_index


class ViewHighlightState:
    """保存单个视图的高亮状态 / Store per-view highlight state."""

    def __init__(self):
        self.entries = {}
        self.last_hover_point = None
        self.last_hover_at = 0.0


_VIEW_STATES = {}
_GLOBAL_HIGHLIGHTS = {}
_FREE_PALETTE_SLOTS = []
_NEXT_PALETTE_INDEX = 0
HOVER_POINT_TTL_SECONDS = 1.2


def _load_settings():
    return sublime.load_settings(PLUGIN_SETTINGS_FILE)


def _normalize_word(word, case_sensitive):
    if case_sensitive:
        return word
    return word.lower()


def _is_valid_word_region(view, region):
    if region.empty():
        return False
    return bool(view.substr(region).strip())


def _is_word_char(ch):
    return ch.isalnum() or ch == "_"


def _resolve_hover_word_region(view, state):
    """
    功能 / Purpose:
        解析当前悬浮词区域，并在悬浮信息过期时安全回退。
        Resolve hover word region and safely fallback when hover is stale.

    实现流程 / Steps:
        1. 检查 last_hover_point 是否存在且在有效期内，若有效则直接取悬浮词。
           Validate last_hover_point with TTL; use hover word when valid.
        2. 若悬浮点不可用，仅在“单光标+空选区”时回退到光标词。
           Fallback to caret word only when single caret and empty selection.
        3. 若存在非空选区（如 Ctrl+F 遗留），返回 None 防止误高亮。
           Return None for non-empty selection to avoid false highlights.

    参数 / Args:
        view: 当前编辑视图对象 / Current editor view.
        state: 视图高亮状态（含最近悬浮点） / View highlight state with hover data.

    返回值 / Returns:
        sublime.Region 或 None / A valid region or None.
    """
    hover_point = state.last_hover_point
    hover_is_fresh = (time.time() - state.last_hover_at) <= HOVER_POINT_TTL_SECONDS
    if hover_point is not None and hover_is_fresh:
        if 0 <= hover_point < view.size():
            ch = view.substr(sublime.Region(hover_point, hover_point + 1))
            if _is_word_char(ch):
                hover_region = view.word(hover_point)
                if _is_valid_word_region(view, hover_region):
                    return hover_region

    if not view.sel():
        return None
    if len(view.sel()) != 1:
        return None

    caret_region = view.sel()[0]
    if not caret_region.empty():
        return None

    point = caret_region.begin()
    if point < 0 or point >= view.size():
        return None

    ch = view.substr(sublime.Region(point, point + 1))
    if not _is_word_char(ch):
        return None

    fallback_region = view.word(point)
    if not _is_valid_word_region(view, fallback_region):
        return None
    return fallback_region


def _build_match_pattern(word, whole_word):
    escaped = re.escape(word)
    if whole_word:
        return r"\b{}\b".format(escaped)
    return escaped


def _find_word_regions(view, word, case_sensitive, whole_word):
    """
    功能 / Purpose:
        在当前视图查找目标词的全部匹配区域。
        Find all matched regions of target word in current view.

    实现流程 / Steps:
        1. 按配置构建匹配模式（整词或普通）并转义特殊字符。
           Build pattern by config and escape special chars.
        2. 组合查找标志（是否忽略大小写）。
           Compose search flags (case sensitivity).
        3. 调用 find_all 返回命中区域列表。
           Call find_all and return matched regions.

    参数 / Args:
        view: 当前视图对象 / Current view.
        word: 目标词文本 / Target word text.
        case_sensitive: 是否区分大小写 / Case-sensitive flag.
        whole_word: 是否仅整词匹配 / Whole-word-only flag.

    返回值 / Returns:
        命中区域列表 / List of matched regions.
    """
    flags = 0
    if not case_sensitive:
        flags |= sublime.IGNORECASE
    pattern = _build_match_pattern(word, whole_word)
    return view.find_all(pattern, flags)


def _get_or_create_state(view):
    view_id = view.id()
    state = _VIEW_STATES.get(view_id)
    if state is None:
        state = ViewHighlightState()
        _VIEW_STATES[view_id] = state
    return state


def _acquire_palette_slot(palette_size):
    """
    功能 / Purpose:
        从全局颜色池分配槽位，保证跨文件同词同色。
        Allocate a global palette slot for consistent color across files.

    实现流程 / Steps:
        1. 调色板为空时回退到 0。
           Fallback to 0 when palette is empty.
        2. 优先复用已释放槽位。
           Reuse released slot first.
        3. 否则按全局指针轮转分配。
           Otherwise allocate by round-robin cursor.

    参数 / Args:
        palette_size: 调色板长度 / Palette size.

    返回值 / Returns:
        颜色槽位索引 / Palette slot index.
    """
    global _NEXT_PALETTE_INDEX
    if palette_size <= 0:
        return 0
    if _FREE_PALETTE_SLOTS:
        return _FREE_PALETTE_SLOTS.pop(0)
    slot = _NEXT_PALETTE_INDEX % palette_size
    _NEXT_PALETTE_INDEX += 1
    return slot


def _release_palette_slot(slot, palette_size):
    """
    功能 / Purpose:
        释放颜色槽位，供后续新词复用。
        Release palette slot for future reuse.

    实现流程 / Steps:
        1. 校验调色板长度，避免无效处理。
           Validate palette size to avoid invalid operations.
        2. 槽位归一化到合法范围。
           Normalize slot into valid range.
        3. 去重后加入空闲池并排序。
           Deduplicate then append and sort free slots.

    参数 / Args:
        slot: 待释放槽位 / Slot to release.
        palette_size: 调色板长度 / Palette size.

    返回值 / Returns:
        无 / None.
    """
    if palette_size <= 0:
        return
    normalized_slot = slot % palette_size
    if normalized_slot in _FREE_PALETTE_SLOTS:
        return
    _FREE_PALETTE_SLOTS.append(normalized_slot)
    _FREE_PALETTE_SLOTS.sort()


def _compose_region_key(word_key, palette_slot):
    return "{}::{}::{}".format(REGION_KEY_PREFIX, palette_slot, word_key)


def _add_regions_with_scope(view, region_key, regions, scope_name):
    flags = sublime.DRAW_NO_OUTLINE
    view.add_regions(region_key, regions, scope_name, "", flags)


def _erase_regions(view, region_key):
    view.erase_regions(region_key)


def _iter_all_file_views():
    """
    功能 / Purpose:
        遍历当前会话全部文件视图，用于跨文件同步。
        Iterate all file views for cross-file synchronization.

    实现流程 / Steps:
        1. 遍历所有窗口和视图。
           Iterate all windows and their views.
        2. 过滤无效或面板视图。
           Filter invalid/panel views.
        3. 返回可操作的文件视图列表。
           Return operable file view list.

    参数 / Args:
        无 / None.

    返回值 / Returns:
        视图列表 / List of views.
    """
    views = []
    for window in sublime.windows():
        for view in window.views():
            if view is None:
                continue
            if hasattr(view, "element") and view.element() is not None:
                continue
            views.append(view)
    return views


def _add_word_highlight_to_view(view, word_key, word, palette_slot, scope_name, case_sensitive, whole_word):
    """
    功能 / Purpose:
        在指定视图添加目标词高亮并更新状态。
        Add target-word highlight to a view and update state.

    实现流程 / Steps:
        1. 查找视图内全部匹配区域。
           Find all matched regions in the view.
        2. 生成 region key 并写入高亮。
           Build region key and apply highlight.
        3. 更新该视图状态，供后续删除与同步使用。
           Update per-view state for future remove/sync.

    参数 / Args:
        view: 目标视图 / Target view.
        word_key: 规范化词键 / Normalized word key.
        word: 原始词文本 / Original word text.
        palette_slot: 颜色槽位 / Palette slot.
        scope_name: 背景 scope / Background scope.
        case_sensitive: 大小写敏感开关 / Case-sensitive flag.
        whole_word: 整词匹配开关 / Whole-word-only flag.

    返回值 / Returns:
        是否成功添加 / True if added, otherwise False.
    """
    regions = _find_word_regions(view, word, case_sensitive, whole_word)
    if not regions:
        return False
    region_key = _compose_region_key(word_key, palette_slot)
    _add_regions_with_scope(view, region_key, regions, scope_name)
    state = _get_or_create_state(view)
    state.entries[word_key] = WordHighlightEntry(word, region_key, palette_slot)
    return True


def _remove_word_highlight_from_view(view, word_key):
    """
    功能 / Purpose:
        从指定视图移除某词高亮并清理状态。
        Remove a word highlight from a view and clear state.

    实现流程 / Steps:
        1. 查找视图状态中的词条记录。
           Locate word entry in view state.
        2. 擦除对应 region。
           Erase corresponding region.
        3. 删除状态记录，保持一致性。
           Delete state entry to keep consistency.

    参数 / Args:
        view: 目标视图 / Target view.
        word_key: 规范化词键 / Normalized word key.

    返回值 / Returns:
        无 / None.
    """
    state = _get_or_create_state(view)
    entry = state.entries.get(word_key)
    if entry is None:
        return
    _erase_regions(view, entry.region_key)
    del state.entries[word_key]


def _sync_global_highlights_to_view(view):
    """
    功能 / Purpose:
        将全局高亮词同步到指定视图，确保新文件继承高亮。
        Sync global highlighted words to a view so new files inherit highlights.

    实现流程 / Steps:
        1. 读取配置（大小写、整词、调色板）。
           Load config (case, whole-word, palette).
        2. 遍历全局高亮词并计算颜色 scope。
           Iterate global words and compute scope.
        3. 对目标视图补齐高亮。
           Apply missing highlights to target view.

    参数 / Args:
        view: 目标视图对象 / Target view.

    返回值 / Returns:
        无 / None.
    """
    if view is None:
        return
    if view.size() <= 0:
        return

    settings = _load_settings()
    case_sensitive = bool(settings.get("case_sensitive", False))
    whole_word = bool(settings.get("whole_word_only", True))
    palette_scopes = settings.get("palette_scopes", DEFAULT_PALETTE_SCOPES)
    if not isinstance(palette_scopes, list) or not palette_scopes:
        palette_scopes = DEFAULT_PALETTE_SCOPES
    if not palette_scopes:
        return

    for word_key, entry in _GLOBAL_HIGHLIGHTS.items():
        scope_name = palette_scopes[entry.palette_index % len(palette_scopes)]
        _add_word_highlight_to_view(
            view,
            word_key,
            entry.word,
            entry.palette_index,
            scope_name,
            case_sensitive,
            whole_word,
        )


class F8WordHighlightHoverListener(sublime_plugin.EventListener):
    """
    功能 / Purpose:
        监听悬浮事件并记录每个视图最近悬浮点，供 F8 命令使用。
        Listen hover events and record latest hover point for F8 command.

    实现流程 / Steps:
        1. 过滤非文本悬浮区域。
           Filter non-text hover zones.
        2. 获取或创建视图状态。
           Get or create view state.
        3. 保存悬浮点和时间戳。
           Save hover point and timestamp.

    参数 / Args:
        view: 当前视图 / Current view.
        point: 悬浮文本点 / Hover text point.
        hover_zone: 悬浮区域类型 / Hover zone type.

    返回值 / Returns:
        无 / None.
    """

    def on_hover(self, view, point, hover_zone):
        if hover_zone != sublime.HOVER_TEXT:
            return
        if point < 0 or point >= view.size():
            return

        state = _get_or_create_state(view)
        state.last_hover_point = point
        state.last_hover_at = time.time()

    def on_close(self, view):
        """
        功能 / Purpose:
            视图关闭时清理状态，避免无效引用驻留。
            Clear state when view closes to avoid stale references.

        实现流程 / Steps:
            1. 按 view.id() 定位状态。
               Locate state by view.id().
            2. 删除对应状态项。
               Remove matching state entry.
            3. 不执行阻塞操作。
               Perform no blocking operations.

        参数 / Args:
            view: 即将关闭视图 / Closing view.

        返回值 / Returns:
            无 / None.
        """
        _VIEW_STATES.pop(view.id(), None)

    def on_load(self, view):
        """
        功能 / Purpose:
            文件加载后同步全局高亮，使新文件继承已有高亮。
            Sync global highlights after file load.

        实现流程 / Steps:
            1. 接收加载完成的视图对象。
               Receive loaded view object.
            2. 调用全局同步逻辑补齐高亮。
               Apply global sync to add highlights.
            3. 不执行阻塞等待。
               No blocking wait.

        参数 / Args:
            view: 刚加载视图 / Newly loaded view.

        返回值 / Returns:
            无 / None.
        """
        _sync_global_highlights_to_view(view)

    def on_activated(self, view):
        """
        功能 / Purpose:
            视图激活时补齐高亮，覆盖重载或延迟加载场景。
            Re-sync highlights on view activation for reload/lazy-load scenarios.

        实现流程 / Steps:
            1. 获取当前视图状态并清理旧悬浮点。
               Get state and clear stale hover point.
            2. 按全局状态同步高亮。
               Re-sync highlights from global state.
            3. 保持幂等，重复调用无副作用。
               Keep idempotent behavior.

        参数 / Args:
            view: 当前激活视图 / Activated view.

        返回值 / Returns:
            无 / None.
        """
        state = _get_or_create_state(view)
        state.last_hover_point = None
        _sync_global_highlights_to_view(view)


class F8ToggleHoverWordHighlightCommand(sublime_plugin.TextCommand):
    """
    功能 / Purpose:
        按 F8 切换悬浮词高亮：未高亮则新增，已高亮则取消（跨文件同步）。
        Toggle hover-word highlight on F8 with cross-file synchronization.

    实现流程 / Steps:
        1. 读取配置与视图状态并解析目标词。
           Load config/state and resolve target word.
        2. 若词已高亮，则全局删除并释放颜色槽位。
           If highlighted, remove globally and release palette slot.
        3. 若未高亮，则在各视图添加高亮并写入全局状态。
           If not highlighted, add to views and save global state.

    参数 / Args:
        edit: Sublime 编辑上下文 / Sublime edit context.

    返回值 / Returns:
        无 / None.
    """

    def run(self, edit):
        view = self.view
        state = _get_or_create_state(view)
        settings = _load_settings()

        case_sensitive = bool(settings.get("case_sensitive", False))
        whole_word = bool(settings.get("whole_word_only", True))
        palette_scopes = settings.get("palette_scopes", DEFAULT_PALETTE_SCOPES)
        if not isinstance(palette_scopes, list) or not palette_scopes:
            palette_scopes = DEFAULT_PALETTE_SCOPES

        word_region = _resolve_hover_word_region(view, state)
        if word_region is None:
            return

        word = view.substr(word_region)
        if not word:
            return

        word_key = _normalize_word(word, case_sensitive)
        global_entry = _GLOBAL_HIGHLIGHTS.get(word_key)
        if global_entry is not None:
            for each_view in _iter_all_file_views():
                _remove_word_highlight_from_view(each_view, word_key)
            _release_palette_slot(global_entry.palette_index, len(palette_scopes))
            del _GLOBAL_HIGHLIGHTS[word_key]
            return

        palette_slot = _acquire_palette_slot(len(palette_scopes))
        scope_name = palette_scopes[palette_slot % len(palette_scopes)]
        has_any_match = False
        for each_view in _iter_all_file_views():
            added = _add_word_highlight_to_view(
                each_view,
                word_key,
                word,
                palette_slot,
                scope_name,
                case_sensitive,
                whole_word,
            )
            if added:
                has_any_match = True

        if not has_any_match:
            _release_palette_slot(palette_slot, len(palette_scopes))
            return

        _GLOBAL_HIGHLIGHTS[word_key] = WordHighlightEntry(
            word,
            _compose_region_key(word_key, palette_slot),
            palette_slot,
        )
