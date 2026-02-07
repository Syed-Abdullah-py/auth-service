import httpx
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_verification():
    print("🚀 Starting MVP Verification...")
    
    # Generate unique emails
    ts = int(time.time())
    owner_email = f"owner_{ts}@example.com"
    doctor_email = f"doctor_{ts}@example.com"
    password = "secretpassword"
    
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Register Owner
        print(f"\n1️⃣  Registering Owner ({owner_email})...")
        resp = client.post("/auth/register", json={"email": owner_email, "password": password})
        if resp.status_code != 200:
            print(f"❌ Failed to register owner: {resp.text}")
            return
        print("✅ Owner registered")
        
        # 2. Login Owner
        print("\n2️⃣  Logging in Owner...")
        resp = client.post("/auth/login", data={"username": owner_email, "password": password})
        if resp.status_code != 200:
            print(f"❌ Failed to login owner: {resp.text}")
            return
        owner_token = resp.json()["access_token"]
        print("✅ Owner logged in")
        
        # 3. Create Workspace
        print("\n3️⃣  Creating Workspace 'Clinic A'...")
        headers_owner = {"Authorization": f"Bearer {owner_token}"}
        resp = client.post("/workspaces", json={"name": "Clinic A"}, headers=headers_owner)
        if resp.status_code != 200:
            print(f"❌ Failed to create workspace: {resp.text}")
            return
        workspace_data = resp.json()
        workspace_id = workspace_data["id"]
        print(f"✅ Workspace 'Clinic A' created (ID: {workspace_id})")
        
        # 4. Get Workspaces (Owner)
        print("\n4️⃣  Verifying Owner Workspaces...")
        resp = client.get("/workspaces", headers=headers_owner)
        workspaces = resp.json()
        if not any(w["workspace_id"] == workspace_id and w["role"] == "OWNER" for w in workspaces):
            print(f"❌ Owner not found as OWNER in workspace list: {workspaces}")
            return
        print("✅ Owner verified as OWNER")
        
        # 5. Register Doctor
        print(f"\n5️⃣  Registering Doctor ({doctor_email})...")
        resp = client.post("/auth/register", json={"email": doctor_email, "password": password})
        if resp.status_code != 200:
            print(f"❌ Failed to register doctor: {resp.text}")
            return
        print("✅ Doctor registered")
        
        # 6. Login Doctor
        print("\n6️⃣  Logging in Doctor...")
        resp = client.post("/auth/login", data={"username": doctor_email, "password": password})
        if resp.status_code != 200:
            print(f"❌ Failed to login doctor: {resp.text}")
            return
        doctor_token = resp.json()["access_token"]
        print("✅ Doctor logged in")
        
        # 7. Add Doctor to Workspace (by Owner)
        print("\n7️⃣  Adding Doctor to Workspace...")
        resp = client.post(
            f"/workspaces/{workspace_id}/members", 
            params={"workspace_id": workspace_id, "email": doctor_email, "role": "DOCTOR"},
            headers=headers_owner
        )
        if resp.status_code != 200:
            print(f"❌ Failed to add doctor: {resp.text}")
            return
        print("✅ Doctor added to workspace")
        
        # 8. Get Workspaces (Doctor)
        print("\n8️⃣  Verifying Doctor Workspaces...")
        headers_doctor = {"Authorization": f"Bearer {doctor_token}"}
        resp = client.get("/workspaces", headers=headers_doctor)
        workspaces = resp.json()
        if not any(w["workspace_id"] == workspace_id and w["role"] == "DOCTOR" for w in workspaces):
            print(f"❌ Doctor not found as DOCTOR in workspace list: {workspaces}")
            return
        print("✅ Doctor verified as DOCTOR")
        
        # 9. Test Protected Routes
        print("\n9️⃣  Testing Protected Routes...")
        
        # Owner -> /users (Allowed: OWNER, ADMIN)
        resp = client.post("/users", headers={**headers_owner, "X-Workspace-Id": str(workspace_id)})
        if resp.status_code == 200:
            print("✅ Owner accessed /users (Allowed)")
        else:
            print(f"❌ Owner blocked from /users: {resp.status_code} {resp.text}")
            
        # Doctor -> /users (Allowed: OWNER, ADMIN) -> Should Fail
        resp = client.post("/users", headers={**headers_doctor, "X-Workspace-Id": str(workspace_id)})
        if resp.status_code == 403:
            print("✅ Doctor blocked from /users (Correctly Forbidden)")
        else:
            print(f"❌ Doctor accessed /users (Should be Forbidden): {resp.status_code}")
            
        # Doctor -> /patients (Allowed: OWNER, ADMIN, DOCTOR)
        resp = client.get("/patients", headers={**headers_doctor, "X-Workspace-Id": str(workspace_id)})
        if resp.status_code == 200:
            print("✅ Doctor accessed /patients (Allowed)")
        else:
            print(f"❌ Doctor blocked from /patients: {resp.status_code} {resp.text}")
            
    print("\n🎉 Verification Complete!")

if __name__ == "__main__":
    try:
        run_verification()
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        print("Ensure the server is running on http://127.0.0.1:8000")
