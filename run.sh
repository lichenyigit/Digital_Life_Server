#!/bin/bash

# 服务配置
SERVICE_CMD="python SocketServer.py --chatVer 3 --APIKey [] --brainwash False --model gpt-3.5-turbo --stream False --character paimon"
SERVICE_PORT=8800

# 检查端口是否被占用并返回对应的PID
get_port_pid() {
  netstat -tunlp | grep ":${SERVICE_PORT} " | awk '{print $7}' | cut -d'/' -f1
}

# 启动服务
start_service() {
  while true; do
    PID=$(get_port_pid)
    if [ -z "$PID" ]; then
      echo "*** Starting service on port ${SERVICE_PORT}..."
      $SERVICE_CMD &
      SERVICE_PID=$!
      echo "*** Service started with PID ${SERVICE_PID}. Waiting for 60 seconds..."
      sleep 60
      NEW_PID=$(get_port_pid)
      if [ -n "$NEW_PID" ] && [ "$NEW_PID" -eq "$SERVICE_PID" ]; then
        echo "*** Service successfully started and running with PID ${SERVICE_PID}."
        break
      else
        echo "*** Service failed to start. Retrying..."
      fi
    else
      echo "*** Port ${SERVICE_PORT} is in use by PID ${PID}. Killing process..."
      kill -9 $PID
      sleep 60  # 确保端口释放
    fi
  done
}

# 监控并重启服务
monitor_service() {
  start_service
  while true; do
	# 获取当前分钟数
	current_minute=$(date +%M)
	# 检查是否为整点（00分）或30分
	# if [ "$current_minute" = "00" ] || [ "$current_minute" = "30" ] || [ "$current_minute" = "20" ]  || [ "$current_minute" = "10" ]  || [ "$current_minute" = "40" ]  || [ "$current_minute" = "50" ] ; then
	if [ "$current_minute" = "00" ] || [ "$current_minute" = "30" ] ; then
		formatted_date=$(date '+%Y年%m月%d日 %H时%M分%S秒')
		echo " "
		echo " "
		echo " "
		echo " "
		echo " "
		echo "*** $formatted_date  ---  当前时间是整点或30分"
		echo "*** Restarting service..."
		PID=$(get_port_pid)
		kill -9 ${PID}
		wait ${PID} 2>/dev/null
		sleep 60
		start_service
	fi
  done
}

# 捕获退出信号并停止服务
trap "echo 'Stopping service...'; kill ${SERVICE_PID}; wait ${SERVICE_PID}; exit" SIGINT SIGTERM

# 启动服务并监控
monitor_service
