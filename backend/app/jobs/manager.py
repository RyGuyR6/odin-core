from app.jobs.models import Job


class JobManager:

    def __init__(self):
        self.jobs = {}

    def create(self, tool, payload):

        job = Job(
            tool=tool,
            payload=payload,
        )

        self.jobs[job.id] = job

        return job

    def get(self, job_id):

        return self.jobs[job_id]


manager = JobManager()
