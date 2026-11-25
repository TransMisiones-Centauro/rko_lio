# ROS 2 Jazzy image with RKO-LIO, built from this repository.
#
# Build from the root of the repository:
#   podman build -f container/Dockerfile -t ghcr.io/transmisiones-centauro/rko_lio:latest .
#   docker build -f container/Dockerfile -t ghcr.io/transmisiones-centauro/rko_lio:latest .

FROM docker.io/osrf/ros:jazzy-desktop-full

# The source code of this repository
COPY . /ros2_ws/src/rko_lio

WORKDIR /ros2_ws
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rosdep update --rosdistro "${ROS_DISTRO}" \
    && rosdep install --from-paths src --ignore-src -r -y \
    && rm -rf /var/lib/apt/lists/*
RUN . /opt/ros/${ROS_DISTRO}/setup.sh \
    && colcon build --packages-select rko_lio \
    && echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

# Functional test, used by the GitHub workflow (see container/test/).
COPY container/test /test

CMD ["bash"]
