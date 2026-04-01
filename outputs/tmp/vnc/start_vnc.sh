#!/bin/bash


# Start Xvfb (Virtual Framebuffer)
export DISPLAY=:99
Xvfb $DISPLAY -screen 0 1920x1080x24 &
XVFB_PID=$!
echo "Xvfb started with PID: $XVFB_PID"

# Wait for Xvfb to start
sleep 2

# Start x11vnc server
x11vnc -display $DISPLAY -forever -shared -rfbport 5900 -nopw -bg -o /tmp/x11vnc.log
X11VNC_PID=$!
echo "x11vnc started with PID: $X11VNC_PID"

# Start websockify for noVNC
websockify --web=/usr/share/novnc 6080 localhost:5900 &
WEBSOCKIFY_PID=$!
echo "websockify started with PID: $WEBSOCKIFY_PID"

# Save PIDs for cleanup
echo "$XVFB_PID" > /tmp/xvfb.pid
echo "$X11VNC_PID" > /tmp/x11vnc.pid
echo "$WEBSOCKIFY_PID" > /tmp/websockify.pid

echo ""
echo "=================================================="
echo "VNC Server Ready!"
echo "=================================================="
echo "noVNC URL: http://localhost:6080/vnc.html"
echo "VNC Port: 5900"
echo "Display: :99"
echo "=================================================="
echo ""
echo "Press Ctrl+C to stop all services"

# Keep script running
wait
