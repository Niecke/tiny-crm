cd backend
.venv/bin/uvicorn app.main:app --reload
# --reload watches files and restarts on save — essential for development



podman-compose up -d      # start postgres
podman-compose down       # stop (data persists in volume)
podman-compose down -v    # stop + wipe all data
