"""Minimal Chinese Tkinter shell for the fake-only development demo."""

from __future__ import annotations

import argparse
import queue
import threading
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, messagebox, ttk

from acoustic_ladder.audio.ess import generate_ess, spec_from_audio_config
from acoustic_ladder.config.bundle import load_config
from acoustic_ladder.config.models import AudioConfig
from acoustic_ladder.ui.controller import (
    Confirmation,
    ExperimentWizardController,
    FakeDemoCaptureRunner,
    WizardError,
    WizardSnapshot,
    WizardState,
)
from acoustic_ladder.ui.plans import WizardPlans, load_wizard_plans

FAKE_MODE_WARNING = "当前未连接真实硬件\uff0c不会播放或录音"
REASSEMBLY_ID = "demo-reassembly-1"
MODULE_DESCRIPTIONS = {
    "BLK": "封闭件",
    "B28": "2.8 mm 桥件",
    "B32": "3.2 mm 桥件",
    "B40": "4.0 mm 桥件",
}

STATE_TEXT = {
    WizardState.WAITING_USER_ASSEMBLY: "等待用户装配",
    WizardState.READY: "准备开始",
    WizardState.RUNNING_REPEAT_1: "正在执行重复 1/2",
    WizardState.RUNNING_REPEAT_2: "正在执行重复 2/2",
    WizardState.CONDITION_COMPLETE: "当前条件完成",
    WizardState.BETWEEN_REPEATS: "两次测量之间",
    WizardState.PAUSED: "已暂停",
    WizardState.CANCELLED: "已取消",
    WizardState.ERROR: "出错",
    WizardState.ALL_COMPLETE: "全部完成",
}


def create_demo_controller(
    project_root: Path,
    session_id: str,
    *,
    recover: bool,
    demo_data_root: Path | None = None,
) -> tuple[WizardPlans, ExperimentWizardController]:
    """Build a fake-only controller without importing or calling a real backend."""

    root = project_root.resolve()
    plans = load_wizard_plans(root)
    loaded = load_config(
        "audio",
        root / "tests/fixtures/audio/ess_offline_development.yaml",
        project_root=root,
    )
    if not isinstance(loaded.model, AudioConfig):
        raise WizardError("development audio fixture did not load as AudioConfig")
    samples = generate_ess(spec_from_audio_config(loaded.model)).samples
    runner = FakeDemoCaptureRunner(samples)
    session_root = (demo_data_root or root / "development" / "demo") / session_id
    factory = ExperimentWizardController.recover if recover else ExperimentWizardController
    controller = factory(
        plan=plans.demo_plan,
        runner=runner,
        session_id=session_id,
        session_root=session_root,
    )
    return plans, controller


class ExperimentWizardWindow:
    """Tk widgets and main-thread dispatch around the display-independent controller."""

    def __init__(
        self,
        root: Tk,
        *,
        plans: WizardPlans,
        controller: ExperimentWizardController,
    ) -> None:
        self.root = root
        self.plans = plans
        self.controller = controller
        self._messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._closing = False
        self._ui_error = ""
        self._status_vars = {
            name: StringVar(root)
            for name in (
                "stage",
                "session",
                "condition",
                "repeat",
                "overall",
                "program_state",
                "last_result",
                "error",
                "next_action",
            )
        }
        self._node_vars = {f"N{index}": StringVar(root) for index in range(1, 7)}
        self._confirmation_vars = {
            confirmation: BooleanVar(root, value=False) for confirmation in Confirmation
        }
        self._build()
        self._refresh(self.controller.snapshot())
        self.root.protocol("WM_DELETE_WINDOW", self._request_close)
        self.root.after(100, self._poll)

    def _build(self) -> None:
        self.root.title("Acoustic Ladder V1.3 — 模拟实验向导")
        self.root.minsize(940, 720)
        outer = ttk.Frame(self.root, padding=12)
        outer.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(
            outer, text="项目: Acoustic Ladder V1.3", font=("TkDefaultFont", 13, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="当前模式: 模拟演练 / FAKE BACKEND").grid(
            row=1, column=0, sticky="w", pady=(3, 0)
        )
        warning = ttk.Label(outer, text=FAKE_MODE_WARNING, foreground="#b00020")
        warning.grid(row=2, column=0, sticky="ew", pady=(3, 8))

        top = ttk.LabelFrame(outer, text="顶部状态区", padding=8)
        top.grid(row=3, column=0, sticky="ew")
        labels = (
            ("Stage", "stage"),
            ("Session", "session"),
            ("Reassembly", None),
            ("当前条件", "condition"),
            ("当前测量重复", "repeat"),
            ("总体进度", "overall"),
        )
        for row, (label, key) in enumerate(labels):
            ttk.Label(top, text=f"{label}: ").grid(row=row, column=0, sticky="e")
            if key is None:
                ttk.Label(top, text=REASSEMBLY_ID).grid(row=row, column=1, sticky="w")
            else:
                ttk.Label(top, textvariable=self._status_vars[key]).grid(
                    row=row, column=1, sticky="w"
                )

        formal = "; ".join(
            f"Stage {item.stage}: {item.condition_count} 条件 / {item.sweep_count} sweeps"
            for item in self.plans.formal_preview.stages
        )
        ttk.Label(
            top,
            text=(
                f"正式计划预览 (只读): {formal}; "
                f"总装配 {self.plans.formal_preview.total_assembly_confirmations} / "
                f"总 sweeps {self.plans.formal_preview.total_sweeps}"
            ),
            wraplength=850,
        ).grid(row=len(labels), column=0, columnspan=2, sticky="w", pady=(6, 0))

        assembly = ttk.LabelFrame(outer, text="[用户操作] 当前装配区", padding=8)
        assembly.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        for index, node_id in enumerate(self._node_vars):
            box = ttk.LabelFrame(assembly, text=node_id, padding=7)
            box.grid(row=0, column=index, padx=3, sticky="nsew")
            assembly.columnconfigure(index, weight=1)
            ttk.Label(box, textvariable=self._node_vars[node_id], justify="center").grid()

        confirmations = ttk.LabelFrame(outer, text="[用户操作] 装配与安全确认", padding=8)
        confirmations.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        confirmation_text = {
            Confirmation.ASSEMBLY_COMPLETE: "我已按 N1-N6 提示完成装配",
            Confirmation.HEADPHONES_OFF: "我已确认耳机没有佩戴在耳朵上",
            Confirmation.PLACEMENT_CORRECT: "我已确认装置及输入/输出端位置正确",
        }
        self._confirmation_buttons = {}
        for row, confirmation in enumerate(Confirmation):
            button = ttk.Checkbutton(
                confirmations,
                text=confirmation_text[confirmation],
                variable=self._confirmation_vars[confirmation],
                command=partial(self._set_confirmation, confirmation),
            )
            button.grid(row=row, column=0, sticky="w")
            self._confirmation_buttons[confirmation] = button

        execution = ttk.LabelFrame(outer, text="[程序执行] Fake capture", padding=8)
        execution.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        for row, (label, key) in enumerate(
            (
                ("程序状态", "program_state"),
                ("最近结果", "last_result"),
                ("错误", "error"),
                ("下一步", "next_action"),
            )
        ):
            ttk.Label(execution, text=f"{label}: ").grid(row=row, column=0, sticky="ne")
            ttk.Label(
                execution,
                textvariable=self._status_vars[key],
                wraplength=760,
            ).grid(row=row, column=1, sticky="w")

        controls = ttk.Frame(outer)
        controls.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self._start_button = ttk.Button(
            controls, text="开始当前条件测量", command=self._start_capture
        )
        self._start_button.grid(row=0, column=0, padx=3)
        self._pause_button = ttk.Button(controls, text="暂停", command=self._pause)
        self._pause_button.grid(row=0, column=1, padx=3)
        self._resume_button = ttk.Button(controls, text="继续", command=self._resume)
        self._resume_button.grid(row=0, column=2, padx=3)
        self._stop_button = ttk.Button(controls, text="紧急停止", command=self._stop)
        self._stop_button.grid(row=0, column=3, padx=3)
        ttk.Button(controls, text="退出", command=self._request_close).grid(row=0, column=4, padx=3)

    def _set_confirmation(self, confirmation: Confirmation) -> None:
        try:
            snapshot = self.controller.set_confirmation(
                confirmation, self._confirmation_vars[confirmation].get()
            )
            self._ui_error = ""
        except WizardError as exc:
            self._ui_error = str(exc)
            snapshot = self.controller.snapshot()
        self._refresh(snapshot)

    def _start_capture(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._capture_worker, daemon=True)
        self._worker.start()
        self._refresh(self.controller.snapshot())

    def _capture_worker(self) -> None:
        try:
            self._messages.put(("snapshot", self.controller.run_current_condition()))
        except Exception as exc:
            self._messages.put(("error", exc))

    def _pause(self) -> None:
        self._run_action(self.controller.request_pause)

    def _resume(self) -> None:
        self._run_action(self.controller.resume)

    def _stop(self) -> None:
        self._run_action(self.controller.emergency_stop)

    def _run_action(self, action: Callable[[], WizardSnapshot]) -> None:
        try:
            snapshot = action()
            self._ui_error = ""
        except WizardError as exc:
            self._ui_error = str(exc)
            snapshot = self.controller.snapshot()
        self._refresh(snapshot)

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self._messages.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                if not isinstance(payload, WizardSnapshot):
                    self._ui_error = "后台线程返回了无效结果"
                else:
                    self._ui_error = ""
                    self._refresh(payload)
            else:
                self._ui_error = f"后台执行失败: {payload}"
                self._refresh(self.controller.snapshot())
        if self._worker is not None and self._worker.is_alive():
            self._refresh(self.controller.snapshot())
        if self._closing and (self._worker is None or not self._worker.is_alive()):
            self.controller.save_state()
            self.root.destroy()
            return
        self.root.after(100, self._poll)

    def _request_close(self) -> None:
        self._closing = True
        if self._worker is not None and self._worker.is_alive():
            self.controller.emergency_stop()
            self._status_vars["next_action"].set("正在取消 fake capture, 安全结束后退出")
            return
        self.controller.save_state()
        self.root.destroy()

    def _refresh(self, snapshot: WizardSnapshot) -> None:
        condition = snapshot.condition
        self._status_vars["stage"].set(str(condition.stage))
        self._status_vars["session"].set(snapshot.session_id)
        self._status_vars["condition"].set(
            f"{snapshot.condition_index + 1}/{snapshot.condition_count} — "
            f"{condition.condition_label}"
        )
        self._status_vars["repeat"].set(
            f"{snapshot.completed_repeat_count}/{snapshot.total_repeat_count}"
        )
        completed_sweeps = (
            snapshot.condition_index * snapshot.total_repeat_count + snapshot.completed_repeat_count
        )
        self._status_vars["overall"].set(
            f"{completed_sweeps}/"
            f"{snapshot.condition_count * snapshot.total_repeat_count} demo sweeps"
        )
        self._status_vars["program_state"].set(STATE_TEXT[snapshot.state])
        self._status_vars["last_result"].set(snapshot.last_capture_summary)
        self._status_vars["error"].set(self._ui_error or snapshot.error_message or "无")
        self._status_vars["next_action"].set(self._next_action(snapshot.state))
        node_states = {node.node_id: node.module_id for node in condition.nodes}
        for node_id, node_variable in self._node_vars.items():
            module_id = node_states[node_id]
            description = MODULE_DESCRIPTIONS.get(module_id, "仓库 canonical 模块")
            node_variable.set(f"{module_id}\n{description}")
        confirmation_enabled = snapshot.state in {
            WizardState.WAITING_USER_ASSEMBLY,
            WizardState.READY,
        }
        for confirmation, confirmation_variable in self._confirmation_vars.items():
            confirmation_variable.set(snapshot.confirmations[confirmation])
            self._confirmation_buttons[confirmation].configure(
                state="normal" if confirmation_enabled else "disabled"
            )
        running = self._worker is not None and self._worker.is_alive()
        self._start_button.configure(
            state="normal" if snapshot.can_start and not running else "disabled"
        )
        self._pause_button.configure(
            state="normal"
            if snapshot.state
            in {
                WizardState.WAITING_USER_ASSEMBLY,
                WizardState.READY,
                WizardState.BETWEEN_REPEATS,
                WizardState.RUNNING_REPEAT_1,
                WizardState.RUNNING_REPEAT_2,
            }
            else "disabled"
        )
        self._resume_button.configure(
            state="normal" if snapshot.state is WizardState.PAUSED else "disabled"
        )

    @staticmethod
    def _next_action(state: WizardState) -> str:
        if state is WizardState.WAITING_USER_ASSEMBLY:
            return "[用户操作] 按 N1-N6 装配并完成三项确认"
        if state is WizardState.READY:
            return "[用户操作] 点击“开始当前条件测量”"
        if state in {WizardState.RUNNING_REPEAT_1, WizardState.RUNNING_REPEAT_2}:
            return "[程序执行] 正在运行 fake backend, 请等待"
        if state is WizardState.PAUSED:
            return "[用户操作] 可点击“继续”或“紧急停止”"
        if state is WizardState.ALL_COMPLETE:
            return "Demo 已全部完成; 没有产生正式实验结论"
        if state in {WizardState.ERROR, WizardState.CANCELLED}:
            return "流程已停止; 检查错误或退出后从安全边界恢复"
        return "[程序执行] 更新 demo 进度"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Acoustic Ladder fake-only Tkinter demo wizard")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--session-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    session_id = args.session_id or datetime.now().strftime("demo-%Y%m%d-%H%M%S")
    root = Tk()
    state_path = (
        args.project_root.resolve() / "development" / "demo" / session_id / "session_state.json"
    )
    recover = False
    if state_path.exists():
        recover = messagebox.askyesno(
            "继续模拟演练?",
            f"检测到 Session {session_id} 的保存状态。是否从安全边界继续?",
            parent=root,
        )
        if not recover:
            messagebox.showerror(
                "拒绝覆盖",
                "已有 demo 状态不会被覆盖。请改用新的 --session-id。",
                parent=root,
            )
            root.destroy()
            return 2
    try:
        plans, controller = create_demo_controller(args.project_root, session_id, recover=recover)
    except Exception as exc:
        messagebox.showerror("启动失败", str(exc), parent=root)
        root.destroy()
        return 1
    ExperimentWizardWindow(root, plans=plans, controller=controller)
    root.mainloop()
    return 0
