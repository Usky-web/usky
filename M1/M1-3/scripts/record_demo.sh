#!/usr/bin/env bash
# M1-3 录屏用的单窗口演示脚本（照这个敲，画面里每一步都有明确结果）
# 用法：bash scripts/record_demo.sh
# 录制：Windows 自带录屏 Win+Alt+R（或 Win+G 打开 Game Bar 再点录制）

cd "$(dirname "$0")/.." || exit 1
source /opt/ros/humble/setup.bash
source install/setup.bash 2>/dev/null

BAG="$HOME/m13_bag"
OUT="demo_out"

pause() {
  echo ""
  printf '──────── 按回车继续 ────────\n'
  read -r _
}

cleanup() {
  pkill -9 -f static_tf_publisher 2>/dev/null
  pkill -9 -f projection_node 2>/dev/null
  pkill -9 -f "ros2 bag play" 2>/dev/null
}
trap cleanup EXIT

echo "=============================================================="
echo " M1-3 演示：TF 树 + 时间同步 + 点云投影 + use_sim_time 对比"
echo "=============================================================="
cleanup
sleep 1

# ---------------------------------------------------------------- 1
echo ""
echo "[第 1 步] 外参真值长什么样（所有 TF 数值都来自它，代码里没有写死）"
grep -E "^laser_link:|^camera_link:|^  parent:|^  xyz:|^  - |^camera_intrinsics:|^  f" extrinsics.yaml | head -20
pause

# ---------------------------------------------------------------- 2
echo "[第 2 步] 准备数据：bag 必须放 WSL 原生盘（放 /mnt/c 会卡住）"
if [ ! -d "$BAG" ]; then
  python3 make_bag.py --frames 100 --out "$BAG" | tail -6
else
  echo "已有 bag：$BAG （$(ros2 bag info "$BAG" 2>/dev/null | grep Duration)）"
  echo "对比：直接把 bag 放 /mnt/c 时 ros2 topic hz /scan 会 9 秒零条（README 第九节）"
fi
pause

# ---------------------------------------------------------------- 3
echo "[第 3 步] 启动 TF + 投影节点（use_sim_time = TRUE）"
rm -rf "$OUT"; mkdir -p "$OUT"
rm -f /tmp/demo_true.log
timeout --kill-after=3 60 ros2 launch m1_three m1_three.launch.py \
    use_sim_time:=true extrinsics_file:=extrinsics.yaml \
    output_dir:="$OUT" max_images:=2 slop:=0.06 > /tmp/demo_true.log 2>&1 &
sleep 5
grep "\[TF\]" /tmp/demo_true.log
pause

echo "[第 4 步] 回放 bag（--clock 会发 /clock，节点才走仿真时间）"
ros2 bag play "$BAG" --clock --rate 1.0 2>/dev/null | tail -2
sleep 2
echo ""
echo ">>> 关键证据 1（节点时钟 == 消息时间戳）"
grep "\[CLOCK\]" /tmp/demo_true.log
echo ">>> 配对情况"
grep -E "已配对|已存图" /tmp/demo_true.log | tail -4
ls -la "$OUT"
pause

# ---------------------------------------------------------------- 5
echo "[第 5 步] 同一个 bag，只把 use_sim_time 改成 FALSE"
cleanup; sleep 1
rm -f /tmp/demo_false.log
timeout --kill-after=3 60 ros2 launch m1_three m1_three.launch.py \
    use_sim_time:=false extrinsics_file:=extrinsics.yaml \
    output_dir:="$OUT" max_images:=0 slop:=0.06 > /tmp/demo_false.log 2>&1 &
sleep 5
ros2 bag play "$BAG" --clock 2>/dev/null | tail -2
sleep 2
echo ""
echo ">>> 关键证据 2（节点墙钟 vs 仿真时间戳，差 ≈ 55 年）"
grep "\[CLOCK\]" /tmp/demo_false.log
pause

# ---------------------------------------------------------------- 6
echo "[第 6 步] 结论"
cat <<'EOF'
  1) use_sim_time=true + bag --clock  → 节点时钟=0.2s，首帧 stamp=0.2s，差≈0，一切自洽
  2) use_sim_time=false              → 节点时钟=1.79e9s，差≈1.79e9s（≈55.6 年）
     本例仍能出图，是因为它只搬运 header.stamp、TF 查询用"最新变换"；
     一旦用 now() 打戳/判超时/算延迟/做插值，就会全错（topic delay 报几千万秒、
     lookup_transform 报 extrapolation into the past）。
  3) 只设 use_sim_time=true 但回放忘了 --clock → 节点时钟停 0，定时器不触发。
     两件事必须成对出现。
EOF
cleanup
echo ""
echo "演示结束。图在 $OUT/ 里（演示用目录，不影响交付的 projection_0*.png）"
