#!/bin/bash
set -e

VM_NAME="vm"
URL="https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
BASE_DIR="/var/lib/libvirt/images"
WORK_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$WORK_DIR/noble-server-cloudimg-amd64.img"
VM_DISK="$BASE_DIR/$VM_NAME.qcow2"
SEED_ISO="$BASE_DIR/seed.iso"

if [ ! -f "$BASE" ]; then
    wget -O "$BASE" "$URL"
fi

if [ ! -f "$VM_DISK" ]; then
    sudo cp "$BASE" "$VM_DISK"
    sudo qemu-img resize "$VM_DISK" 10G
fi

cloud-localds \
    "$WORK_DIR/seed.iso" \
    "$WORK_DIR/cloud-init/user-data" \
    "$WORK_DIR/cloud-init/meta-data"

sudo cp "$WORK_DIR/seed.iso" "$SEED_ISO"

if ! sudo virsh net-info default | grep -q "Active:.*yes"; then
    sudo virsh net-start default
fi

sudo virt-install \
    --name "$VM_NAME" \
    --memory 2048 \
    --vcpus 2 \
    --import \
    --disk path="$VM_DISK",format=qcow2 \
    --disk path="$SEED_ISO",device=cdrom \
    --os-variant ubuntu24.04 \
    --network network=default \
    --graphics none \
    --console pty,target_type=serial \
    --noautoconsole

