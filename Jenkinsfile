pipeline {
    agent any

    stages {
        stage('Build Docker Image') {
            steps {
                sh 'docker build -t system-knowledge-bot:ci .'
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                docker run -d -p 8001:8000 system-knowledge-bot:ci
                sleep 5
                curl -f http://localhost:8001/health
                '''
            }
        }
    }
}
