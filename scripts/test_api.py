import sys
import time
import uuid
import subprocess
from pathlib import Path

import libvirt
import requests


BASE_URL = "http://127.0.0.1:8000"
IMAGE = "ubuntu24"
VM_NAME = f"test-{uuid.uuid4().hex[:8]}"
PROJECT_DIR = Path(__file__).resolve().parent.parent

MAX_VMS = 5
MAX_MEMORY = 4096
MAX_VCPUS = 4
MAX_TOTAL_MEMORY = 8192
MAX_TOTAL_VCPUS = 8

passed = 0
failed = 0
skipped = 0
created_vms = []
server = None


def check(name, condition):
  global passed, failed
  if condition:
    print(f"PASS: {name}")
    passed += 1
  else:
    print(f"FAIL: {name}")
    failed += 1


def skip(name, reason):
  global skipped
  print(f"SKIP: {name} ({reason})")
  skipped += 1


def request(method, path, **kwargs):
  return requests.request(method, BASE_URL + path, timeout=240, **kwargs)


def get_vms():
  response = request("GET", "/vms")
  if response.status_code != 200:
    raise RuntimeError(response.text)
  return response.json()


def find_vm(name):
  return next((vm for vm in get_vms() if vm["name"] == name), None)


def wait_for_stop(name):
  for _ in range(60):
    vm = find_vm(name)
    if vm is not None and vm["state"] == "stopped":
      return True
    time.sleep(2)
  return False


def get_resources():
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")
  try:
    ds = c.listAllDomains()
    return {
      "count": len(ds),
      "memory": sum(d.maxMemory() // 1024 for d in ds),
      "vcpus": sum(d.info()[3] for d in ds)
    }
  finally:
    c.close()


def create_vm(name, memory=1024, vcpus=1):
  response = request("POST", "/vms", json={"name": name, "memory": memory, "vcpus": vcpus, "image": IMAGE})
  if response.status_code == 200 or find_vm(name) is not None:
    created_vms.append(name)
  return response


def delete_vm(name):
  if name not in created_vms:
    return False
  vm = find_vm(name)
  if vm is None:
    return True
  c = libvirt.open("qemu:///system")
  if c is None:
    raise RuntimeError("Connection failed.")
  try:
    try:
      d = c.lookupByName(name)
    except libvirt.libvirtError:
      d = None
    if d is not None and d.isActive():
      d.destroy()
  finally:
    c.close()
  if find_vm(name) is not None:
    response = request("DELETE", f"/vms/{name}")
    if response.status_code != 200:
      print(f"DELETE {name}: {response.status_code}, {response.text}")
  return find_vm(name) is None


def cleanup_names(names):
  for name in reversed(names):
    if not delete_vm(name):
      raise RuntimeError(f"Could not delete {name}")


def cleanup():
  global failed
  for name in reversed(created_vms):
    try:
      if not delete_vm(name):
        print(f"FAIL: Cleanup {name}")
        failed += 1
    except (requests.RequestException, RuntimeError, ValueError, libvirt.libvirtError) as e:
      print(f"FAIL: Cleanup {name}: {e}")
      failed += 1


def start_server():
  global server
  server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd=PROJECT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
  )
  for _ in range(30):
    if server.poll() is not None:
      raise RuntimeError("FastAPI failed to start.")
    try:
      if requests.get(f"{BASE_URL}/openapi.json", timeout=2).status_code == 200:
        return
    except requests.RequestException:
      pass
    time.sleep(1)
  raise RuntimeError("FastAPI startup timeout.")


def stop_server():
  global server
  if server is None:
    return
  if server.poll() is None:
    server.terminate()
    try:
      server.wait(timeout=15)
    except subprocess.TimeoutExpired:
      server.kill()
      server.wait()
  server = None


def test_vm_count_limit():
  resources = get_resources()
  needed = MAX_VMS - resources["count"]
  if needed < 0:
    skip("VM count limit", "VM count already exceeds limit")
    return
  if resources["memory"] + needed * 512 > MAX_TOTAL_MEMORY or resources["vcpus"] + needed > MAX_TOTAL_VCPUS:
    skip("VM count limit", "Not enough resources")
    return
  names = []
  try:
    for _ in range(needed):
      name = f"count-{uuid.uuid4().hex[:8]}"
      response = create_vm(name, memory=512, vcpus=1)
      if response.status_code != 200:
        check("VM count limit", False)
        return
      names.append(name)
    response = create_vm(f"count-{uuid.uuid4().hex[:8]}", memory=512, vcpus=1)
    check("VM count limit", response.status_code == 400 and "VM Limit" in response.text)
  finally:
    cleanup_names(names)


def test_total_memory_limit():
  resources = get_resources()
  free_memory = MAX_TOTAL_MEMORY - resources["memory"]
  free_vcpus = MAX_TOTAL_VCPUS - resources["vcpus"]
  free_slots = MAX_VMS - resources["count"]
  if free_memory < 1024 or free_vcpus < 3 or free_slots < 3:
    skip("Total memory limit", "Not enough resources")
    return
  first_memory = min(MAX_MEMORY, free_memory - 512)
  second_memory = free_memory - first_memory
  if not 512 <= second_memory <= MAX_MEMORY or not 512 <= first_memory <= MAX_MEMORY:
    skip("Total memory limit", "Cannot fill memory quota")
    return
  names = []
  try:
    for memory in (first_memory, second_memory):
      name = f"memory-{uuid.uuid4().hex[:8]}"
      response = create_vm(name, memory=memory)
      if response.status_code != 200:
        check("Total memory limit", False)
        return
      names.append(name)
    response = create_vm(f"memory-{uuid.uuid4().hex[:8]}", memory=512)
    check("Total memory limit", response.status_code == 400 and "Total Memory Limit" in response.text)
  finally:
    cleanup_names(names)


def test_total_vcpu_limit():
  resources = get_resources()
  free_memory = MAX_TOTAL_MEMORY - resources["memory"]
  free_vcpus = MAX_TOTAL_VCPUS - resources["vcpus"]
  free_slots = MAX_VMS - resources["count"]
  if free_memory < 1536 or free_vcpus < 2 or free_slots < 3:
    skip("Total vCPU limit", "Not enough resources")
    return
  first_vcpus = min(MAX_VCPUS, free_vcpus - 1)
  second_vcpus = free_vcpus - first_vcpus
  if not 1 <= second_vcpus <= MAX_VCPUS or not 1 <= first_vcpus <= MAX_VCPUS:
    skip("Total vCPU limit", "Cannot fill vCPU quota")
    return
  names = []
  try:
    for vcpus in (first_vcpus, second_vcpus):
      name = f"cpu-{uuid.uuid4().hex[:8]}"
      response = create_vm(name, memory=512, vcpus=vcpus)
      if response.status_code != 200:
        check("Total vCPU limit", False)
        return
      names.append(name)
    response = create_vm(f"cpu-{uuid.uuid4().hex[:8]}", memory=512, vcpus=1)
    check("Total vCPU limit", response.status_code == 400 and "Total VCPU Limit" in response.text)
  finally:
    cleanup_names(names)


def test_persistence():
  before = {vm["name"]: vm["state"] for vm in get_vms()}
  stop_server()
  start_server()
  after = {vm["name"]: vm["state"] for vm in get_vms()}
  check("VM persistence", before == after)


def main():
  global failed
  try:
    start_server()
    response = request("GET", "/openapi.json")
    check("API availability", response.status_code == 200)
    response = request("GET", "/vms")
    check("List VMs", response.status_code == 200 and isinstance(response.json(), list))
    response = request("GET", "/images")
    check("List images", response.status_code == 200 and isinstance(response.json(), list))
    if response.status_code != 200:
      raise RuntimeError("Image registry unavailable.")
    if not any(image["name"] == IMAGE for image in response.json()):
      raise RuntimeError(f"Image {IMAGE} is not registered.")
    response = create_vm(f"limit-{uuid.uuid4().hex[:8]}", memory=8192)
    check("Memory limit", response.status_code in (400, 422))
    response = create_vm(f"limit-{uuid.uuid4().hex[:8]}", vcpus=8)
    check("vCPU limit", response.status_code in (400, 422))
    test_vm_count_limit()
    test_total_memory_limit()
    test_total_vcpu_limit()
    response = create_vm(VM_NAME)
    check("Create VM", response.status_code == 200)
    if response.status_code != 200:
      print(response.text)
      return
    check("VM exists", find_vm(VM_NAME) is not None)
    response = create_vm(VM_NAME)
    check("Duplicate VM", response.status_code == 400)
    response = request("GET", f"/vms/{VM_NAME}/stats")
    check("VM monitoring", response.status_code == 200 and all(
      key in response.json() for key in ("cpu_usage_percent", "memory_allocated_mb", "disk_capacity_gb", "disk_used_gb")
    ))
    test_persistence()
    response = request("POST", f"/vms/{VM_NAME}/stop")
    check("Stop VM", response.status_code == 200)
    if response.status_code != 200:
      return
    stopped = wait_for_stop(VM_NAME)
    check("VM stopped", stopped)
    if not stopped:
      print(f"VM state: {find_vm(VM_NAME)}")
      return
    response = request("DELETE", f"/vms/{VM_NAME}")
    check("Delete VM", response.status_code == 200)
    if response.status_code == 200:
      check("VM removed", find_vm(VM_NAME) is None)
  except (requests.RequestException, RuntimeError, ValueError, libvirt.libvirtError) as e:
    print(f"ERROR: {e}")
    check("Script execution", False)
  finally:
    try:
      if server is None or server.poll() is not None:
        start_server()
      cleanup()
    except (requests.RequestException, RuntimeError, ValueError, libvirt.libvirtError) as e:
      print(f"WARNING: Cleanup failed: {e}")
      failed += 1
    stop_server()
    print(f"\nPassed: {passed}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")


if __name__ == "__main__":
  main()
