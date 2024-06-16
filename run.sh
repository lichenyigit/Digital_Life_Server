#!/bin/bash

# 服务配置
SERVICE_CMD="python SocketServer.py --chatVer 3 --APIKey [api-key] --brainwash False --model gpt-3.5-turbo --stream False --character paimon"
SERVICE_PORT=8800
RESTART_INTERVAL=1800  # 100分钟，单位：秒  6000-100分钟  300-5分钟

# 检查端口是否被占用并返回对应的PID
get_port_pid() {
  netstat -tunlp | grep ":${SERVICE_PORT} " | awk '{print $7}' | cut -d'/' -f1
}

# 启动服务
start_service() {
  while true; do
    PID=$(get_port_pid)
    if [ -z "$PID" ]; then
      echo "Starting service on port ${SERVICE_PORT}..."
      $SERVICE_CMD &
      SERVICE_PID=$!
      echo "Service started with PID ${SERVICE_PID}. Waiting for 30 seconds..."
      sleep 30
      NEW_PID=$(get_port_pid)
      if [ -n "$NEW_PID" ] && [ "$NEW_PID" -eq "$SERVICE_PID" ]; then
        echo "Service successfully started and running with PID ${SERVICE_PID}."
        return
      else
        echo "Service failed to start. Retrying..."
      fi
    else
      echo "Port ${SERVICE_PORT} is in use by PID ${PID}. Killing process..."
      kill -9 $PID
      sleep 2  # 确保端口释放
    fi
  done
}

# 监控并重启服务
monitor_service() {
  while true; do
    sleep ${RESTART_INTERVAL}
    echo "Restarting service..."
    kill ${SERVICE_PID}
    wait ${SERVICE_PID} 2>/dev/null
    start_service
  done
}

# 捕获退出信号并停止服务
trap "echo 'Stopping service...'; kill ${SERVICE_PID}; wait ${SERVICE_PID}; exit" SIGINT SIGTERM

# 启动服务并监控
start_service
monitor_service
