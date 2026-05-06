# F8 Word Highlight (Sublime Text 4)

## 中文说明

### 功能
- 鼠标点击到某个单词后按 `F8`：高亮当前文件中所有完全匹配的同词。
- 点击到已高亮单词再次按 `F8`：取消该词高亮。
- 支持多个单词同时高亮，不同单词按固定调色板分配不同背景色。
- 全局同步：在一个文件里高亮的词，会同步到当前已打开的其他文件。

### 文件说明
- `F8WordHighlight.py`：插件核心逻辑（悬浮点跟踪、按词切换、颜色槽位复用、跨文件同步）。
- `Default (Windows).sublime-keymap`：Windows 下将 `F8` 绑定到插件命令。
- `F8WordHighlight.sublime-settings`：可配置项（大小写、整词、调色板）。

### 安装
1. 打开命令面板（`Cmd/Ctrl + Shift + P`）。
2. 选择 `Package Control: Install Package`。
3. 搜索 `F8WordHighlight` 并安装。

### 配置项
- `case_sensitive`：是否大小写敏感，默认 `false`。
- `whole_word_only`：是否只匹配整词，默认 `true`。
- `palette_scopes`：高亮颜色 scope 列表，按槽位轮换复用。

### 使用说明
1. 将鼠标移动或点击到目标单词上（插件会记录最近悬浮位置）。
2. 按 `F8`，该词所有匹配项会被高亮。
3. 再次点击或悬浮同词并按 `F8`，即可取消该词高亮。
4. 可重复对多个不同单词执行该操作，颜色会自动区分。

## English

### Features
- Click a word and press `F8` to highlight all exact matches in the current file.
- Click an already highlighted word and press `F8` again to remove its highlight.
- Supports highlighting multiple words at the same time, with different background colors from a fixed palette.
- Global sync: a highlighted word in one file is synchronized to other currently opened files.

### File Overview
- `F8WordHighlight.py`: Core plugin logic (hover tracking, per-word toggle, palette slot reuse, cross-file sync).
- `Default (Windows).sublime-keymap`: Binds `F8` to the plugin command on Windows.
- `F8WordHighlight.sublime-settings`: Configuration options (case sensitivity, whole-word match, palette).

### Installation
1. Open the Command Palette (`Cmd/Ctrl + Shift + P`).
2. Choose `Package Control: Install Package`.
3. Search for `F8WordHighlight` and install it.

### Settings
- `case_sensitive`: Whether matching is case-sensitive, default is `false`.
- `whole_word_only`: Whether to match whole words only, default is `true`.
- `palette_scopes`: Highlight color scope list, reused by rotating palette slots.

### Usage
1. Move or click the mouse onto the target word (the plugin records the latest hover point).
2. Press `F8` to highlight all matches of the word.
3. Click or hover the same word again and press `F8` to remove its highlight.
4. Repeat this for multiple words; colors are assigned automatically.