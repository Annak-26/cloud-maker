import time
from pathlib import Path
import xml.etree.ElementTree as ET

import libvirt
from prometheus_client import CollectorRegistry, Gauge, generate_latest
from fastapi.responses import Response

BASE_DIR = Path("/var/lib/libvirt/images/cloud-maker")


def vm_stats(name):
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")

  try:
    try:
      d = c.lookupByName(name)
    except libvirt.libvirtError as e:
      if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
        raise ValueError("Virtual machine not found.")
      raise

    if not d.isActive():
      disk = BASE_DIR / f"{name}.qcow2"
      disk_capacity = None
      disk_used = None

      if disk.exists():
        disk_used = disk.stat().st_blocks * 512 / (1024 ** 3)

        try:
          disk_capacity = d.blockInfo(str(disk))[0] / (1024 ** 3)
        except libvirt.libvirtError:
          pass

      return {
        "name": name,
        "state": "stopped",
        "cpu_usage_percent": 0,
        "memory_allocated_mb": d.info()[1] // 1024,
        "memory_used_mb": None,
        "disk_capacity_gb": round(disk_capacity, 2) if disk_capacity is not None else None,
        "disk_used_gb": round(disk_used, 2) if disk_used is not None else None
      }

    cpu1 = d.info()[4]
    time1 = time.monotonic()
    time.sleep(1)
    cpu2 = d.info()[4]
    time2 = time.monotonic()

    cpu_usage = (cpu2 - cpu1) / ((time2 - time1) * 1e9) * 100

    d.setMemoryStatsPeriod(1)
    memory = d.memoryStats()
    memory_used = None

    if "actual" in memory and "unused" in memory:
      memory_used = (memory["actual"] - memory["unused"]) / 1024

    disk = BASE_DIR / f"{name}.qcow2"
    disk_capacity = None
    disk_used = None

    if disk.exists():
      stat = disk.stat()
      disk_used = stat.st_blocks * 512 / (1024 ** 3)

      try:
        disk_info = d.blockInfo(str(disk))
        disk_capacity = disk_info[0] / (1024 ** 3)
      except libvirt.libvirtError:
        pass

    return {
      "name": name,
      "state": "running",
      "cpu_usage_percent": round(cpu_usage, 2),
      "memory_allocated_mb": d.info()[1] // 1024,
      "memory_used_mb": round(memory_used, 2) if memory_used is not None else None,
      "disk_capacity_gb": round(disk_capacity, 2) if disk_capacity is not None else None,
      "disk_used_gb": round(disk_used, 2) if disk_used is not None else None
    }

  finally:
    c.close()


def metrics():
  r = CollectorRegistry()

  vm_memory = Gauge(
    "cloudmaker_vm_memory_bytes",
    "Allocated VM memory in bytes",
    ["vm"],
    registry=r,
  )

  vm_cpu_time = Gauge(
    "cloudmaker_vm_cpu_time_seconds",
    "Total VM CPU time in seconds",
    ["vm"],
    registry=r,
  )

  vm_disk_read = Gauge(
    "cloudmaker_vm_disk_read_bytes_total",
    "Total disk bytes read",
    ["vm"],
    registry=r,
  )

  vm_disk_write = Gauge(
    "cloudmaker_vm_disk_write_bytes_total",
    "Total disk bytes written",
    ["vm"],
    registry=r,
  )

  vm_network_rx = Gauge(
    "cloudmaker_vm_network_rx_bytes_total",
    "Total network bytes received",
    ["vm"],
    registry=r,
  )

  vm_network_tx = Gauge(
    "cloudmaker_vm_network_tx_bytes_total",
    "Total network bytes transmitted",
    ["vm"],
    registry=r,
  )

  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")

  try:
    for d in c.listAllDomains():
      if not d.isActive():
        continue

      name = d.name()
      state, max_memory, memory, vcpus, cpu_time = d.info()

      vm_memory.labels(vm=name).set(memory * 1024)
      vm_cpu_time.labels(vm=name).set(cpu_time / 1e9)

      xml = ET.fromstring(d.XMLDesc())

      disk_read = 0
      disk_write = 0

      for disk in xml.findall("./devices/disk"):
        target = disk.find("target")
        if target is None:
          continue

        device = target.get("dev")
        if device is None:
          continue

        try:
          stats = d.blockStats(device)
          disk_read += stats[1]
          disk_write += stats[3]
        except libvirt.libvirtError:
          continue

      vm_disk_read.labels(vm=name).set(disk_read)
      vm_disk_write.labels(vm=name).set(disk_write)

      network_rx = 0
      network_tx = 0

      for interface in xml.findall("./devices/interface"):
        target = interface.find("target")
        if target is None:
          continue

        device = target.get("dev")
        if device is None:
          continue

        try:
          stats = d.interfaceStats(device)
          network_rx += stats[0]
          network_tx += stats[4]
        except libvirt.libvirtError:
          continue

      vm_network_rx.labels(vm=name).set(network_rx)
      vm_network_tx.labels(vm=name).set(network_tx)

  finally:
    c.close()

  return Response(
    content=generate_latest(r),
    media_type="text/plain; version=0.0.4; charset=utf-8"
  )
