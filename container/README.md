# Running RKO-LIO in a container (Podman or Docker)

These instructions build and run a ROS 2 Jazzy container image with RKO-LIO installed.
They work with both [Podman](https://podman.io/) and [Docker](https://docs.docker.com/), because the two tools
take the same command-line syntax for everything used here. Pick one and set a shell variable so the commands
below can be copied as they are:

```bash
ENGINE=podman   # or: ENGINE=docker
```

Differences between the two:

| | Podman | Docker |
|---|---|---|
| Daemon | None. Containers are child processes of the user | Run by the `dockerd` daemon, usually as root |
| Run as normal user | Yes (rootless by default) | Only if the user is in the `docker` group, or with `sudo` |
| X11 access (`xhost`) | `xhost +local:$USER` | `xhost +local:root` (the container runs as root) |
| Image names | Use fully qualified names (`docker.io/...`, `ghcr.io/...`) | `docker.io/` can be left out |

Podman can also replace Docker transparently: `alias docker=podman`, or install the `podman-docker` package.

## Create the software image

Start a container from the official ROS 2 Jazzy image:

```bash
$ENGINE pull docker.io/osrf/ros:jazzy-desktop-full
$ENGINE run -it --name rko_lio docker.io/osrf/ros:jazzy-desktop-full
```

Inside the container, install RKO-LIO from the ROS 2 package repository:

```bash
apt update && apt -y upgrade
apt install ros-$ROS_DISTRO-rko-lio
exit
```

Save the container as a new image and, optionally, publish it to the GitHub Container Registry.
To push, you must log in first with a GitHub personal access token that has the `write:packages` scope:

```bash
$ENGINE commit rko_lio ghcr.io/transmisiones-centauro/rko_lio:latest
$ENGINE rm rko_lio

$ENGINE login ghcr.io
$ENGINE push ghcr.io/transmisiones-centauro/rko_lio:latest
```

Replace `ghcr.io/transmisiones-centauro/rko_lio` with your own registry and namespace if needed.

## Run the container

Allow the container to open windows on the host X server (needed for RViz):

```bash
xhost +local:$USER   # Podman (rootless)
xhost +local:root    # Docker
```

Then start the container:

```bash
$ENGINE run -it --rm --name rko_lio \
    --env="DISPLAY=$DISPLAY" \
    --env="QT_X11_NO_MITSHM=1" \
    --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
    --device /dev/dri \
    ghcr.io/transmisiones-centauro/rko_lio:latest
```

Useful additional options:

- `--net=host --ipc=host`: share the host network and IPC, so that ROS 2 nodes inside the container can discover
  nodes on the host or on the robot (for example the LiDAR and IMU drivers).
- `--volume="$HOME/bags:/bags:rw"`: make a host directory with rosbags available inside the container.
- `--security-opt label=disable`: on SELinux hosts (Fedora, RHEL), allows the container to access the X11 socket.

Inside the container, launch the odometry as described in the [main README](../README.md#ros):

```bash
ros2 launch rko_lio odometry.launch.py
```
