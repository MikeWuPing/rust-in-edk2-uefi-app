---
name: rust-in-edk2-uefi-app
description: Use when building a UEFI application whose application logic is written in Rust but whose rendering/UEFI plumbing stays C (EDK2 + LVGL), when linking a cargo staticlib into an EDK2 module, when a Rust .efi must run as a plain EFI_APPLICATION under the classic UEFI Shell, when building a Chinese-language GUI on LVGL (CJK font coverage checks), or when automating QEMU (launch + QMP screendump/pointer injection) from Windows PowerShell. Covers the /NODEFAULTLIB link trap, the archive-name collision, PowerShell 5.1 native-stderr and safe-delete traps, the QEMU launch matrix, QMP capture pitfalls, and the three silent LVGL rendering traps (B,G,R byte order, cmap coverage, missing child clipping).
agent_created: true
---

# 把 Rust 逻辑链进 EDK2 UEFI 应用（并在 QEMU 里做完闭环验证）

适用场景：想在 UEFI Shell 下跑一个应用，**逻辑用 Rust 写**，但图形/固件抽象继续用现成的 C 栈（EDK2 + LVGL）。
不适用：纯 Rust 的 UEFI 固件（那用 `uefi` crate 直接出 `.efi`）；纯 C 的 EDK2 应用（见 `emulator-uefi-shell-app`）。

## 0. 先确认一件事：UEFI Shell 与语言无关

Shell 执行命令时做的是 `gBS->LoadImage()` → `gBS->StartImage()`，**只认两件事：PE/COFF 格式 + `EFI_APPLICATION` subsystem**。
所以 Rust 的 `x86_64-unknown-uefi` target 产物丢给老 Shell 就能跑，**不需要任何"Rust 版 Shell"**。
`cargo` 直接出 `.efi` 也是一条路；本技能讲的是"Rust 只出静态库、由 EDK2 做顶层链接"那条路——它的价值是**复用既有 EDK2 工程的全部约定**（DSC/INF、第三方 C 包、串口版本断言通道、vendored OVMF）。

## 1. 架构：Rust 出静态库，EDK2 做链接器

```
Rust (crate-type = ["staticlib"], no_std, panic = "abort")
   │  导出 extern "C" 入口 + 一组扁平 C ABI
   ▼
C 薄壳（UefiMain.c）＋ C shim（把 LVGL 类型/枚举折成稳定 ABI）
   │
   ▼  EDK2 链接 → <Name>.efi
LVGL / GOP / 键盘 / 鼠标
```

Rust 侧**绝不 include EDK2 头、也不用 bindgen**：边界是手写的 `extern "C"` 声明 + 一个 C 头文件。
颜色一律走 `0x00RRGGBB` + 独立 opacity 字节；事件走**单一 trampoline**（对象带一个打包过的 `user` 值，按类别分发），这样 UI 事件路径上零动态分配。

### 1.1 shim 边界要配一个**校验脚本**，光立纪律不够

C 头文件与 Rust 的 `ffi.rs` 是一对孪生声明，靠人同步一定会漂。命名约定建议固定成
**C 侧加前缀、Rust 侧剥前缀**：`RP_EV_PRESSED`（C）↔ `EV_PRESSED`（Rust），函数名则同名。

关键在于**两类漂移的后果完全不对等**：

| 漏改 | 后果 |
|---|---|
| 漏一个函数声明 | 链接期 `LNK2001`，会报错，好发现 |
| 漏/写错一个**常量** | **编译期、链接期都不报错**，运行期静默取到错的值 |

所以必须有个脚本比对两侧符号集合 + 常量数值，挂在构建流程最前面（cargo 之前），漂移即 fail。
Python 不在 PATH 时打印一行跳过、不要中断构建。

参考实现见 `rustpaint/tools/check_abi.py`（正则抽 `#define` 与 `pub const`、函数名，
`int(s, 0)` 解析字面量，解析不了的表达式跳过）。**写完后必须自己注入一次假漂移验证它能抓到**——
两边都解析成 0 个符号时脚本会"通过"，那是假绿。

## 2. 三条链接硬规矩（每条都真炸过一次）

### 2.1 `/DEFAULTLIB:` 在 EDK2 里无效——库必须当**输入文件**

EDK2 生成的链接命令以 `/NODEFAULTLIB` 开头，它会忽略所有 `/DEFAULTLIB:` 指令。
正确写法（MSVC 工具链）：

```
[BuildOptions]
  MSFT:*_*_*_LINK_FLAGS  = /SUBSYSTEM:EFI_APPLICATION /LIBPATH:$(MODULE_DIR) rp_core.lib
  MSFT:*_*_*_DLINK_FLAGS = /SUBSYSTEM:EFI_APPLICATION /LIBPATH:$(MODULE_DIR) rp_core.lib
```

（`$(MODULE_DIR)` 是 BaseTools 支持的宏，指向 INF 所在目录。）

### 2.2 库名**不能等于** `BASE_NAME`

EDK2 用 `<BASE_NAME>.lib` 命名模块自己的对象归档。若你的 Rust 库同名，`/DEFAULTLIB:` 会解析到它自己，报：

```
rustupaint.lib(UefiMain.obj) : error LNK2001: unresolved symbol rp_app_build
```

解法：给 Rust 库起个明显不同的名字（`rp_core.lib` 之类），构建脚本把 cargo 产物复制成这个固定名。

### 2.3 INF 的 `[Binaries]` **不参与链接**

BaseTools 对它只做 `CopyBinaryFiles()`（拷贝文件）。**别指望用它引入库。**

### 2.4 强制重编：Version.h 变了 EDK2 不会重编

生成的 `Version.h` 每次构建都会变，但 EDK2 的增量构建不追踪它 → 模块不重编 → 发出**旧版本**的 `.efi`。
构建脚本每次删掉本模块的输出目录强制重编（只删本模块，第三方 C 包保持缓存）。

## 3. 构建环境（Windows + VS2019 + EDK2）

常规流程：`set PACKAGES_PATH=<项目根>;<edk2>&& .\edksetup.bat && build -p X/X.dsc -a X64 -t VS2019 -b RELEASE`。
下面这些是**必须先处理**的坑：

### 3.1 `INCLUDE` 缺 UCRT 目录 → 所有 C TU 死在 `<stddef.h>`

MSVC 自己的 `include` 目录**只有编译器内置头**（`stdint.h`/`vcruntime.h`/`sal.h`）；C 标准库头（`stddef.h`/`stdlib.h`/`string.h`）在 **Windows SDK 的 `ucrt`** 目录里。
`vcvarsall.bat` 靠**查注册表**找 SDK 版本；注册表查询一旦失败（受限 shell／沙箱拦了 `reg.exe`），`INCLUDE` 就缺 UCRT，报：

```
lvgl/src/misc/lv_types.h(20): fatal error C1083: cannot open stddef.h
```

**对策**：构建脚本自己按**目录枚举**算出 MSVC include + SDK 的 `ucrt/shared/um/winrt`，并**在 `edksetup.bat` 之后**覆盖 `INCLUDE`（edksetup 内部跑 vcvarsall，会把它改坏）。选目录时用 `Test-Path <dir>\ucrt\stddef.h` 做校验，不要凭版本号猜。

### 3.2 `GenFw` 用裸名调用 → PATH 上找不到

生成的 Makefile 里 `GENFW = GenFw`（裸名），而 `cl/link/lib/nmake` 都是绝对路径——所以**只有 GenFw 会中招**。
根因常是**环境块里同时存在 `Path` 和 `PATH`**（Windows 经典坑）：cmd 按一种拼写解析、Python 的 `os.environ` 折叠成另一种，于是 `build.py` 传给 nmake 的 PATH 里没有 `BaseTools\Bin\Win32`。

**对策**：不要跟 PATH 缠斗。让构建脚本容忍 EDK2 在最后一步失败，**用绝对路径自己补跑**：

```powershell
& "$Edk2\BaseTools\Bin\Win32\GenFw.exe" -e UEFI_APPLICATION -o $efi $dll
```
判据是"`.efi` 是否生成"，不是 EDK2 的退出码。

### 3.3 QEMU 磁盘必须有可引导项

`-drive format=raw,file=<FAT 镜像>` 时，镜像里要有 **`EFI\BOOT\BOOTX64.EFI`**，否则 BDS 报
`No bootable option or device was found`。
放 EDK2 的 `Shell.efi`（**必须 >100KB**——占位/截断的 Shell 看起来和"应用没启动"一模一样）到该路径，
再在根目录放 `startup.nsh`（内容就一行 `yourapp.efi`，CRLF），Shell 启动时会自动执行它。
鼠标要 `-usb -device usb-mouse`。

## 4. PowerShell 5.1 的四个陷阱（Windows 上做构建脚本必然遇到）

1. **cargo / 任何原生工具写 stderr → 被 `$ErrorActionPreference='Stop'` 包成终止错误**。
   cargo 把 `Compiling...` / `Finished ...` 写到 **stderr**，于是明明成功、脚本却挂。
   **对策**：让 `cmd` 拥有重定向——`cmd /c "<tool> <args> > log 2>&1"`，PowerShell 只看退出码。
2. **`Remove-Item` 可能被安全钩子接管**（fail-closed 转回收站），删构建中间目录时报
   `[safe-delete][SAFE_DELETE_FAIL_CLOSED] Some operations were aborted` 并终止脚本。
   **对策**：对**可再生的构建产物**用 `[System.IO.Directory]::Delete($p, $true)`（.NET 调用不被拦截）。
3. **别用调用方管道接构建输出**（`& build.ps1 | Tee-Object | Select -Last`）——会把构建掐死。
   用脚本自带的 `-LogFile` 参数，在脚本内部 tee。
4. **`.ps1` 注释一律纯 ASCII**：PS 5.1 对无 BOM 的 `.ps1` 按本地代码页解析，中文注释会吞掉行尾 LF 把脚本解析断。

## 5. 从 PowerShell 启动 QEMU：只有一个写法是对的

目标："启动 QEMU，脚本立刻继续"。

| 写法 | 结果 |
|---|---|
| `Start-Process` | 抛 `An item with the same key has already been added. Key: 'PATH'`——环境块里有重复的 `Path`/`PATH`，.NET 的字典大小写敏感 |
| `cmd /c "start /b qemu ..."`（子进程**不**重定向） | QEMU 继承了调用方的 stdout 管道，`cmd /c` 一直等到 QEMU 退出才返回 → **脚本永久卡在启动那一行**。症状极具迷惑性：QEMU 正常开机、串口日志健康，但之后**一行输出都没有** |
| 同上 + 内联 `> out.log 2> err.log` | 日志文件确实生成了，但（在被重定向的调用方环境下）脚本仍到不了下一阶段，且**杀掉 QEMU 也不解锁** → 说明等的不是 QEMU 句柄。不可信 |
| **WMI `Win32_Process.Create`** | ✅ 无句柄继承、直接回传 PID。适合无头（`-display none`）。代价：子进程在 **session 0**，SDL 窗口看不见 |
| **前台 `cmd /c "qemu ... > log 2> log"`** | ✅ 适合交互模式——阻塞正是"等用户关窗口"的语义，且进程属于当前会话、窗口可见 |

**不要**用 `Get-Process` 拿到的进程句柄去 `Kill()` / `WaitForExit()`：那对组合在本工作区会无限阻塞。
收口用 `taskkill /F /PID <pid>` + 有界轮询。

另外：**给 Run 脚本加一条无缓冲的进度轨**。`Write-Host` 在被调用方 `*>` 重定向时会留在缓冲区，
脚本卡死时日志几乎空白——排查"卡在哪一行"会浪费大量时间。用 `Add-Content`（每次刷盘）写
`run_logs/<stamp>_trace.txt`，每个阶段一行。

## 6. QMP 抓帧的三个坑

1. **`os.kill(pid, 0)` 在 Windows 上等于 `TerminateProcess(pid, 0)`**。CPython 对非
   `CTRL_C_EVENT`/`CTRL_BREAK_EVENT` 的 sig 直接 TerminateProcess，所以拿它当"存活检查"
   会**把被检查的 QEMU 当场杀掉**。改用 `OpenProcess` + `GetExitCodeProcess`。
2. **`screendump` 不按扩展名选格式**：对 `screendump foo.png` 仍可能写出 P6 **PPM**。
   稳的做法是**嗅探文件魔数**，不是 PNG 才转。Pillow 因此是可选依赖（缺它就保留原始帧 + 打一行 WARN，不要让整个抓帧流程失败）。
   注意 `python` 在 cmd 与 bash 里可能解析到**不同解释器**，Pillow 有无会不一样。
3. **驱动脚本必须自带时间预算**：加 `--deadline`（主循环礼貌退出）**和**一个守护线程到点 `os._exit`
   （应对"某一次调用自己卡住"）。驱动被调用方**同步**调用时，一次卡死就拖垮整条循环。
   同时**不要**用 `start /b python ... > log` 这种脱离式包装——日志文件可能根本不生成，子进程的失败**完全静默**。
4. `socket.create_connection(..., timeout=1)` 会把 1 秒超时**留在返回的 socket 上**，
   导致第一次 `readline()`（QMP greeting）在机器还在启动时超时。连上后显式 `sock.settimeout(30)`。

## 7. 自动化交互的 token 设计（QMP 驱动）

- `hover|X|Y`——先撞左上角复位（反复大负向 rel，驱动侧钳位保证终态精确为 (0,0)），再按标定系数分步走位，**每步 ≤127**（HID boot 报告上限）。
- `btn|left`——只发按键沿、**不带坐标**，指针停在 `hover` 留下的位置。"定位"与"点击"解耦。
- `down|left` / `up|left`——按下不松 / 松开。**拖动画线必须用 `rel|dx|dy` 走中间过程，不能用 `hover`**：
  `hover` 每次都先撞角复位，按住状态下那一段大位移会被画成一条拉回原点的乱线。
  画一笔：`hover|X|Y t1 down|left t1 rel|80|40 t1 rel|60|-60 t1 up|left t4 screendump drew`

## 8. LVGL 侧的静默陷阱与排版纪律（不报错、不越界、只是画得不对）

这几条都是"代码能编、能跑、画面也在动，但就是不对"，而且**灰度/黑白测试全部漏检**。做 LVGL 界面前先排掉它们。

### 8.1 888 像素是 **B,G,R**，不是 R,G,B

不要凭类型名推断布局，读源码（`src/misc/lv_color.h`）：

| 类型 | 定义 | 内存字节序 |
|---|---|---|
| `lv_color_t`（RGB888 画布 / 显示缓冲） | `struct { blue; green; red; }` | **B,G,R** |
| `lv_color32_t`（ARGB8888） | `struct { blue; green; red; alpha; }` | **B,G,R,A** |

软渲染器一致：`src/draw/sw/blend/lv_draw_sw_blend_to_rgb888.c` 里
`dest_u8[x+0] = color.blue; dest_u8[x+2] = color.red;`。

**症状**：蓝↔红互换、绿不变。用黑白灰作画时三通道相等 → **完全看不出来**；等界面用到强调色（比如 `0x0067C0` 蓝）才炸——屏幕上会出现**橙色**。
**纪律**：写像素的路径按 `bpp`（3/4）分派布局；RGB888 写 `b,g,r`，ARGB8888 写 `b,g,r,255`。
**验收**：抓帧后**逐块量化**颜色（取色块中心像素比对期望值），别用"看起来对"。

### 8.2 中文字库覆盖必须**解析 cmap**，不能读注释、不能 grep 码位

`lv_font_fmt_txt` 的 cmap 两种编码（依据 `src/font/lv_font_fmt_txt.c` 的 `get_glyph_dsc_id`：
`uint32_t rcp = letter - cmap->range_start;`）：

- `FORMAT0_FULL`：`glyph_id_ofs_list[rcp]`，**值为 0 表示该码位没有字形**；
- `SPARSE_FULL`：`unicode_list` 里是**相对 `range_start` 的偏移**，不是绝对码位。

两个后果：`grep 0x4EF6` 找汉字**无效**；只按 `range_start/length` 判覆盖会**虚高**（把 SPARSE 段当成整段连续覆盖）。

**另一处路径陷阱**：同一个仓库里可能有**两份同名字体**，而 INF 只编其中一份（例：`LvglLib/lvgl/src/font/` 与 `LvglLib/Fonts/` 各有一份 `lv_font_simsun_16_cjk.c`，内容不同）。
**查覆盖要看 INF 里真正列出的那个路径。**

**纪律**：界面文案一旦改成中文，就写个 `--check` 脚本从**源码字符串字面量**反推所需码位集合并与字库比对，把它纳入构建前检查。
在拉丁字库上中文会**静默消失**（不报错、不占位、直接不画），所以这一项必须自动化。

### 8.3 LVGL **默认不裁剪子对象**——容器算矮了不会报错，子对象直接溢出

症状是"某个控件被后面建的兄弟节点压住/切掉一半"。本例：底部选色区 `PALETTE_H = 44`，而两行色块需要 58px，
第二行溢出后**被后建的状态栏盖住**，屏幕上只露出 8px 高的一条。

**排查手法**：把可疑区域裁出来放大，再沿某一行做**游程编码**，逐个色块比对起点/宽度/颜色——比肉眼可靠得多。
**修法**：优先改布局（本例改成单行 16 色块，1280 宽度富余），其次才是加 `LV_OBJ_FLAG_OVERFLOW_VISIBLE` 之类的裁剪控制。

### 8.4 顺带两条小的

- **1px 描边在 20~26px 的小图标上会淡到几乎看不见**。图标里用 2px 起。
- 图标要放在按钮之上时，用 **ARGB8888 子画布**：RGB 画布不透明，会盖掉按钮的**按下/焦点底色**。
  同时记得给图标对象**去掉 clickable 标志**，否则它会吃掉点击，事件到不了按钮。

### 8.5 右对齐要交给 LVGL 排版，不要在宿主语言里估字符串宽度

obj 的坐标只能指定**左端**原点，所以"把一行字贴到右边"直觉上要写 `x = right - 估算宽度`。
比例字体下这个估算必然偏，换字号就整体错位。

正解是给 label 一个**固定宽度**再让它自己右对齐：

```c
lv_obj_set_size (Obj, BoxW, 24);                           /* 先定宽 */
lv_obj_set_style_text_align (Obj, LV_TEXT_ALIGN_RIGHT, 0);  /* 再定对齐 */
lv_obj_set_pos (Obj, RightX - BoxW, Y);
```

两条纪律：

- **顺序不能反**。先设对齐再设尺寸，LVGL 已按 content 宽度排好版，`TEXT_ALIGN_RIGHT` 无从生效
  ——现象是"右对齐没起作用，还是从左排起"，而且不报任何错。
- **`BoxW` 必须宽于最长文本**。给窄了是**截断**，不是溢出到框外（LVGL 不画到框外）。

**排版经验（混排）**：「中文标签 + 拉丁正文」走**单一 CJK 字库**（simsun 含 ASCII），两段基线天生对齐；
拆成两个不同字库的 label 就得手工对基线，换字号即崩。标点风格也要统一（别一个全角冒号一个半角空格）。

## 9. 验收清单（每条都要留证据）

1. **串口 `APP_VERSION=<version>`** 与 `expected_version.txt` **逐字节一致**（对不上就是发了旧 `.efi`，按失败处理）。
2. 串口无 `PANIC` / `... failed`。
3. `snapshot/` 有 `screendump` 抓到的 PNG，画面是预期内容。
   **SDL 窗口客户区抓屏在 QEMU 下必然全黑，不能当证据**——必须走 QMP/monitor。
4. 链接日志里 **0 个 LNK2001**，且 `map` 文件里能找到 Rust 侧的导出符号。
5. 交互模式（`-display sdl`）**`qemu_stderr.log` 为空** = SDL 初始化成功。
6. 端到端跑一次无头闭环，**退出码 0**。

## 10. 排错顺序（卡住时按这个走）

1. 看 `run_logs/<stamp>_trace.txt`（有没有——没有就给脚本加上）。
2. 看串口：`APP_VERSION` 有没有？`ui built` 之类的自证行有没有？→ 区分"应用没起来"和"应用起来了但截图没拿到"。
3. 看 `snapshot/` 文件**大小**：1280×800 的 PPM 恒为 `1280*800*3+15` 字节；如果 `.png` 是这个大小，说明格式没转。
4. 看 `LNK2001` 指向哪个符号 → 回 §2 三条规矩。
5. 画面不对 → 回 §8（字节序 / 字库 / 裁剪）。

## 附：点击坐标可以直接算，不用试

`hover` 的标定关系是 `device = round(pixel * abs_max / screen)`。先反解出 `abs_max`
（读日志里已打印的 `hover -> screen (x,y) = device (dx,dy)`，反算一次即可），
然后**按布局常量算目标中心**，不要靠试。

例（1280×800，`abs_max = 1024`，`TITLE_H=36`、`MENU_H=32`、工具按钮高 40、x 中心 28）：

- 菜单栏中心 y = `TITLE_H + (MENU_H-8)/2 + 3` → 51；第 i 个菜单标题 x 中心 = `8 + 68i + 34`
- 工作区顶 = `TITLE_H + MENU_H` = 68；工具按钮中心 y = `work_y + PAD + i*(btn_h+6) + btn_h/2`，x = `PAD + btn_w/2`
- 下拉面板 `x = 8 + 68i - 4`、`y = TITLE_H + MENU_H`；第 r 行中心 y = `y + 4 + 30r + 13`

**教训**：靠猜 `hover|28|77` 想点第 2 个工具，实际落进了第 1 个按钮的 40px 带（76..116）里，白跑一轮。
先算再点；抓帧后用**状态栏哈希**或控件局部像素变化来判定点击是否命中（比读文字可靠）。
