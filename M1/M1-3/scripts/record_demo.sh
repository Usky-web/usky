#!/usr/bin/env bash
# M1-3 录屏演示（一个窗口走完，每一步停下等你按回车）
# 用法：在 Ubuntu 终端里执行  bash scripts/record_demo.sh

cd "$(dirname "$0")/.." || exit 1
source /opt/ros/humble/setup.bash
source install/setup.bash 2>/dev/null

BAG="$HOME/m13_bag"
OUT="demo_out"

step() {
  echo ""
  echo "=============================================================="
  echo " $1"
  echo "=============================================================="
}
pause() {
  printf '\n>>>>>>>> 按一下回车继续 <<<<<<<<\n'
  read -r _
}
cleanup() {
  pkill -9 -f static_tf_publisher 2>/dev/null
  pkill -9 -f projection_node 2>/dev/null
  pkill -9 -f "ros2 bag play" 2>/dev/null
}
trap cleanup EXIT

clear
echo "  M1-3 演示：TF2 坐标树 ｜ 时间同步 ｜ 点云投影 ｜ use_sim_time 对比"
echo "  （按回车一步一步走，全程约 4 分钟）"
cleanup
sleep 1

# ---------------------------------------------------------------- 1
step "[1/6] 外参真值文件（TF 里的数字全部来自它，代码没写死）"
sed -n '1,40p' extrinsics.yaml
pause

# ---------------------------------------------------------------- 2
step "[2/6] 准备数据（bag 必须放 WSL 原生盘，放 Windows 盘会卡死）"
if [ ! -d "$BAG" ]; then
  python3 make_bag.py --frames 100 --out "$BAG" | tail -7
else
  echo "已有 bag：$BAG"
  ros2 bag info "$BAG" 2>/dev/null | grep -E "Duration|Messages|Topic"
fi
echo ""
echo "对照：同一份 bag 放 /mnt/c 时 ros2 topic hz /scan 连续 9 秒一条都没有"
pause

# ---------------------------------------------------------------- 3
step "[3/6] 启动两个节点：静态 TF 发布器 + 投影节点（use_sim_time = TRUE）"
rm -rf "$OUT"; mkdir -p "$OUT"
rm -f /tmp/demo_true.log
timeout --kill-after=3 200 ros2 launch m1_three m1_three.launch.py \
    use_sim_time:=true extrinsics_file:=extrinsics.yaml \
    output_dir:="$OUT" max_images:=2 slop:=0.06 > /tmp/demo_true.log 2>&1 &
sleep 6
echo ">>> 四段父子关系（这就是题面要的 TF 树）："
grep "\[TF\]" /tmp/demo_true.log
pause

step "[4/6] 回放 bag（--clock 会发 /clock，节点才跟着仿真时间走）"
ros2 bag play "$BAG" --clock --rate 2.0 2>/dev/null
sleep 3
echo ""
echo ">>> 证据 1：节点时钟 vs 消息时间戳（同一基准，差只有零点几秒）"
grep "\[CLOCK\]" /tmp/demo_true.log
echo ">>> 同步配对情况："
grep -E "已配对|已存图" /tmp/demo_true.log | tail -3
pause

# ---------------------------------------------------------------- 5
step "[5/6] 同一个 bag、同样 --clock，只把 use_sim_time 改成 FALSE"
cleanup; sleep 1
rm -f /tmp/demo_false.log
timeout --kill-after=3 200 ros2 launch m1_three m1_three.launch.py \
    use_sim_time:=false extrinsics_file:=extrinsics.yaml \
    output_dir:="$OUT" max_images:=0 slop:=0.06 > /tmp/demo_false.log 2>&1 &
sleep 6
ros2 bag play "$BAG" --clock --rate 2.0 2>/dev/null
sleep 3
echo ""
echo ">>> 证据 2：节点用墙钟，消息是仿真时间，差 ≈ 55 年"
grep "\[CLOCK\]" /tmp/demo_false.log
pause

# ---------------------------------------------------------------- 6
step "[6/6] 结论（这三句是要背下来的）"
cat <<'EOF'
  1) use_sim_time=true + bag --clock
     → 节点时钟跟着 /clock 走，和消息戳同一个基准（差 0.2~0.5 s，纯投递滞后）。
  2) use_sim_time=false
     → 节点用墙钟 1.79e9 s，消息戳 0.1 s，差 ≈ 55 年。
       本节点还能出图，是因为它只搬运 header.stamp、TF 查"最新变换"；
       一旦用 now() 打戳 / 判超时 / 算延迟 / 做插值 → 全错
       （现象：ros2 topic delay 报几千万秒、lookup_transform 报 extrapolation into the past）。
  3) 只设 true 但回放忘了 --clock
     → 节点时钟停在 0，定时器不触发。两件事必须成对出现。
EOF
cleanup
echo ""
echo ">>> 投影图（等下会自动弹出来一张）："
ls -la "$OUT" 2>/dev/null
PNG="$(ls "$OUT"/projection_*.png 2>/dev/null | head -1)"
if [ -n "$PNG" ]; then
  echo "打开：$PNG"
  explorer.exe "$(wslpath -w "$PNG")" >/dev/null 2>&1 &
fi
echo ""
echo "演示结束。"
