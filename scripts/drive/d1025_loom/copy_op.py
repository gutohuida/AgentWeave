import sqlite3, sys
src = sqlite3.connect("file:C:/Users/huida/.agentweave/hub/data/agentweave.db?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
src.close()
repo = sys.argv[2]
for t in ["ai_jobs", "apscheduler_jobs", "loops", "manager_jobs", "inbound_queue_entries", "api_keys", "operator_credentials"]:
    dst.execute(f"delete from {t}")
dst.execute("update projects set working_directory=? where id='proj-d85a82bf4216'", (repo,))
dst.execute("update projects set working_directory='C:/nonexistent-aw-drive/'||id where id!='proj-d85a82bf4216'")
dst.commit()
print(dst.execute("select id, working_directory from projects").fetchall())
print(dst.execute("select status, count(*) from runs group by status").fetchall())
