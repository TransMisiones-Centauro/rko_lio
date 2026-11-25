#!/usr/bin/env python3
"""Publish a synthetic, static LiDAR + IMU stream and check that an odometry node produces sensible output.

The sensor sits still in the middle of a box-shaped room with a few boxes inside. The node publishes:
  - /clock          simulated time (launch the odometry with use_sim_time = true)
  - IMU topic       sensor_msgs/Imu at 200 Hz, measuring only gravity
  - LiDAR topic     sensor_msgs/PointCloud2 at 10 Hz, Velodyne-style fields:
                    x, y, z, intensity, time (offset from the start of the scan), ring

It counts the messages on the odometry topic and exits with code 0 if enough of them arrive
and the estimated position stays close to the origin, or 1 otherwise.
"""

import argparse
import sys

import numpy as np
import rclpy
from builtin_interfaces.msg import Time
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Imu, PointCloud2, PointField
from std_msgs.msg import Header

IMU_RATE = 200.0
LIDAR_EVERY = 20             # one point cloud every 20 IMU messages = 10 Hz
SCAN_PERIOD = 0.1            # seconds


def room_points(step=0.1, size=(10.0, 8.0, 3.0)):
    """Points on the faces of a box-shaped room around the sensor, plus three boxes inside it."""
    sx, sy, sz = (s / 2 for s in size)
    xs = np.arange(-sx, sx + 1e-6, step)
    ys = np.arange(-sy, sy + 1e-6, step)
    zs = np.arange(-1.0, sz * 2 - 1.0 + 1e-6, step)  # floor 1 m below the sensor
    faces = []
    for x in (-sx, sx):
        y, z = np.meshgrid(ys, zs)
        faces.append(np.stack([np.full(y.size, x), y.ravel(), z.ravel()], axis=1))
    for y in (-sy, sy):
        x, z = np.meshgrid(xs, zs)
        faces.append(np.stack([x.ravel(), np.full(x.size, y), z.ravel()], axis=1))
    for z in (zs[0], zs[-1]):
        x, y = np.meshgrid(xs, ys)
        faces.append(np.stack([x.ravel(), y.ravel(), np.full(x.size, z)], axis=1))
    for cx, cy, w in ((3.0, 2.5, 1.0), (-3.0, -2.0, 0.6), (1.5, -3.0, 0.8)):
        a = np.arange(-w / 2, w / 2 + 1e-6, step)
        b = np.arange(-1.0, 0.5, step)
        u, v = np.meshgrid(a, b)
        for off in (-w / 2, w / 2):
            faces.append(np.stack([np.full(u.size, cx + off), cy + u.ravel(), v.ravel()], axis=1))
            faces.append(np.stack([cx + u.ravel(), np.full(u.size, cy + off), v.ravel()], axis=1))
    return np.concatenate(faces)


def make_cloud_template(time_scale, rings=16):
    """Structured array with the Velodyne point layout, sorted by acquisition time within the scan."""
    pts = room_points()
    azimuth = np.arctan2(pts[:, 1], pts[:, 0])                       # -pi .. pi
    t = (azimuth + np.pi) / (2 * np.pi) * SCAN_PERIOD                # 0 .. 0.1 s
    elevation = np.degrees(np.arctan2(pts[:, 2], np.hypot(pts[:, 0], pts[:, 1])))
    ring = np.clip(((elevation + 30.0) / 60.0 * rings).astype(int), 0, rings - 1)
    order = np.argsort(t)

    dtype = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('intensity', '<f4'),
                      ('time', '<f4'), ('ring', '<u2'), ('_pad', '<u2')])
    cloud = np.zeros(len(pts), dtype=dtype)
    cloud['x'], cloud['y'], cloud['z'] = pts[order, 0], pts[order, 1], pts[order, 2]
    cloud['intensity'] = 100.0
    cloud['time'] = t[order] * time_scale
    cloud['ring'] = ring[order]
    fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1),
        PointField(name='time', offset=16, datatype=PointField.FLOAT32, count=1),
        PointField(name='ring', offset=20, datatype=PointField.UINT16, count=1),
    ]
    return cloud, fields


class SyntheticSensors(Node):
    def __init__(self, args):
        super().__init__('synthetic_sensors_test')
        self.args = args
        self.clock_pub = self.create_publisher(Clock, '/clock', 10)
        self.imu_pub = self.create_publisher(Imu, args.imu_topic, 100)
        self.pc_pub = self.create_publisher(PointCloud2, args.cloud_topic, 10)
        self.create_subscription(Odometry, args.odom_topic, self.odom_cb, 10)

        cloud, fields = make_cloud_template(args.time_scale)
        self.cloud_msg = PointCloud2(
            height=1, width=len(cloud), fields=fields, is_bigendian=False,
            point_step=cloud.dtype.itemsize, row_step=cloud.dtype.itemsize * len(cloud),
            data=cloud.tobytes(), is_dense=True)

        self.tick = 0
        self.odom_count = 0
        self.last_position = None
        self.done = False
        self.create_timer(1.0 / IMU_RATE, self.step)

    def stamp(self):
        ns = 1_000_000_000 + int(self.tick * 1e9 / IMU_RATE)  # start at t = 1 s
        return Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000)

    def step(self):
        stamp = self.stamp()
        self.clock_pub.publish(Clock(clock=stamp))

        imu = Imu()
        imu.header = Header(stamp=stamp, frame_id=self.args.imu_frame)
        imu.orientation.w = 1.0
        imu.linear_acceleration.z = 9.80665
        self.imu_pub.publish(imu)

        if self.tick % LIDAR_EVERY == 0:
            self.cloud_msg.header = Header(stamp=stamp, frame_id=self.args.lidar_frame)
            self.pc_pub.publish(self.cloud_msg)

        self.tick += 1
        if self.tick >= self.args.duration * IMU_RATE:
            self.done = True

    def odom_cb(self, msg):
        self.odom_count += 1
        p = msg.pose.pose.position
        self.last_position = np.array([p.x, p.y, p.z])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--imu-topic', default='imu_raw')
    parser.add_argument('--cloud-topic', default='points_raw')
    parser.add_argument('--odom-topic', required=True)
    parser.add_argument('--imu-frame', default='imu')
    parser.add_argument('--lidar-frame', default='lidar')
    parser.add_argument('--time-scale', type=float, default=1.0,
                        help='unit of the per-point time field, as a multiplier from seconds (1e6 = microseconds)')
    parser.add_argument('--duration', type=float, default=25.0, help='seconds of simulated data')
    parser.add_argument('--min-odom', type=int, default=50, help='minimum number of odometry messages')
    parser.add_argument('--max-drift', type=float, default=0.5, help='maximum final distance to the origin (m)')
    args = parser.parse_args()

    rclpy.init()
    node = SyntheticSensors(args)
    while rclpy.ok() and not node.done:
        rclpy.spin_once(node, timeout_sec=0.1)
    for _ in range(20):  # let the odometry process the last messages
        rclpy.spin_once(node, timeout_sec=0.1)

    count, pos = node.odom_count, node.last_position
    node.destroy_node()
    rclpy.shutdown()

    print(f'Odometry messages received on {args.odom_topic}: {count} (minimum {args.min_odom})')
    if pos is not None:
        drift = float(np.linalg.norm(pos))
        print(f'Final position: {pos.round(3).tolist()}, drift {drift:.3f} m (maximum {args.max_drift} m)')
    if count < args.min_odom or pos is None or np.linalg.norm(pos) > args.max_drift:
        print('TEST FAILED')
        return 1
    print('TEST PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
