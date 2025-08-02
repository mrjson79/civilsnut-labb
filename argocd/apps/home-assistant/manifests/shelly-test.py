#!/usr/bin/env python3
"""
Test script to debug Shelly device connectivity using aioshelly library
This replicates what Home Assistant does when connecting to Shelly devices
"""

import asyncio
import aiohttp
import time
from aioshelly.common import get_info, ConnectionOptions
from aioshelly.block_device import BLOCK_VALUE_UNIT, BlockDevice
from aioshelly.rpc_device import RpcDevice

SHELLY_IP = "192.168.3.178"
SHELLY_PORT = 80

async def test_basic_connection():
    """Test basic HTTP connection to Shelly device"""
    print("=== Testing Basic HTTP Connection ===")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        try:
            start_time = time.time()
            async with session.get(f"http://{SHELLY_IP}/status") as resp:
                duration = time.time() - start_time
                print(f"✓ HTTP /status request successful in {duration:.2f}s")
                print(f"  Status Code: {resp.status}")
                text = await resp.text()
                print(f"  Response length: {len(text)} chars")

        except Exception as e:
            print(f"✗ HTTP /status request failed: {e}")

async def test_aioshelly_get_info():
    """Test aioshelly get_info function (same as Home Assistant uses)"""
    print("\n=== Testing aioshelly get_info ===")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        try:
            start_time = time.time()
            info = await get_info(session, SHELLY_IP, port=SHELLY_PORT)
            duration = time.time() - start_time
            print(f"✓ aioshelly get_info successful in {duration:.2f}s")
            print(f"  Device type: {info.get('type', 'Unknown')}")
            print(f"  MAC: {info.get('mac', 'Unknown')}")
            print(f"  Firmware: {info.get('fw', 'Unknown')}")
            return info

        except Exception as e:
            print(f"✗ aioshelly get_info failed: {e}")
            return None

async def test_block_device_creation():
    """Test creating a BlockDevice instance (Generation 1 Shelly)"""
    print("\n=== Testing BlockDevice Creation ===")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        try:
            start_time = time.time()

            # Create connection options
            options = ConnectionOptions(
                ip_address=SHELLY_IP,
                username=None,
                password=None,
                device_mac=None
            )

            # Create BlockDevice instance
            device = await BlockDevice.create(session, options)
            duration = time.time() - start_time

            print(f"✓ BlockDevice created successfully in {duration:.2f}s")
            print(f"  Device name: {device.name}")
            print(f"  Device type: {device.device_type}")
            print(f"  MAC address: {device.mac}")
            print(f"  Firmware version: {device.firmware_version}")
            print(f"  Number of blocks: {len(device.blocks)}")

            # Test device update
            start_time = time.time()
            await device.update()
            duration = time.time() - start_time
            print(f"✓ Device update successful in {duration:.2f}s")

            return device

        except Exception as e:
            print(f"✗ BlockDevice creation failed: {e}")
            return None

async def test_device_data_fetching():
    """Test fetching device data (what causes the timeout in HA)"""
    print("\n=== Testing Device Data Fetching ===")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        try:
            # Test individual endpoints
            endpoints = ["/status", "/settings", "/shelly", "/ota"]

            for endpoint in endpoints:
                start_time = time.time()
                async with session.get(f"http://{SHELLY_IP}{endpoint}") as resp:
                    duration = time.time() - start_time
                    text = await resp.text()
                    print(f"✓ {endpoint}: {resp.status} in {duration:.2f}s ({len(text)} chars)")

        except Exception as e:
            print(f"✗ Endpoint testing failed: {e}")

async def test_with_different_timeouts():
    """Test with various timeout settings"""
    print("\n=== Testing Different Timeout Settings ===")

    timeouts = [5, 10, 30, 60]

    for timeout_val in timeouts:
        print(f"\nTesting with {timeout_val}s timeout:")
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout_val)
        ) as session:
            try:
                start_time = time.time()
                async with session.get(f"http://{SHELLY_IP}/status") as resp:
                    duration = time.time() - start_time
                    print(f"  ✓ Success in {duration:.2f}s")

            except asyncio.TimeoutError:
                print(f"  ✗ Timeout after {timeout_val}s")
            except Exception as e:
                print(f"  ✗ Error: {e}")

async def test_concurrent_requests():
    """Test multiple concurrent requests (like HA might do)"""
    print("\n=== Testing Concurrent Requests ===")

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        try:
            # Create 5 concurrent requests
            tasks = []
            for i in range(5):
                task = session.get(f"http://{SHELLY_IP}/status")
                tasks.append(task)

            start_time = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start_time

            successes = sum(1 for r in responses if not isinstance(r, Exception))
            print(f"✓ {successes}/5 concurrent requests successful in {duration:.2f}s")

            for i, resp in enumerate(responses):
                if isinstance(resp, Exception):
                    print(f"  Request {i+1}: ✗ {resp}")
                else:
                    resp.close()
                    print(f"  Request {i+1}: ✓ {resp.status}")

        except Exception as e:
            print(f"✗ Concurrent request test failed: {e}")

async def main():
    """Run all tests"""
    print("Shelly Device Debug Test")
    print("=" * 50)
    print(f"Testing device at: {SHELLY_IP}:{SHELLY_PORT}")
    print()

    # Run all tests
    await test_basic_connection()
    info = await test_aioshelly_get_info()

    if info:
        device = await test_block_device_creation()

    await test_device_data_fetching()
    await test_with_different_timeouts()
    await test_concurrent_requests()

    print("\n" + "=" * 50)
    print("Test completed!")

if __name__ == "__main__":
    asyncio.run(main())
