import subprocess

def run_cmd(cmd):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(f"STDOUT: {result.stdout}")
    print(f"STDERR: {result.stderr}")
    return result

# 1. Create User
run_cmd('sudo mysql -e "CREATE USER IF NOT EXISTS \'astra_user\'@\'localhost\' IDENTIFIED BY \'password123\';"')
# 2. Grant Privileges
run_cmd('sudo mysql -e "GRANT ALL PRIVILEGES ON astra360.* TO \'astra_user\'@\'localhost\';"')
# 3. Flush
run_cmd('sudo mysql -e "FLUSH PRIVILEGES;"')
# 4. Verify
run_cmd('mysql -u astra_user -ppassword123 -e "SHOW DATABASES;"')
