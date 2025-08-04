pipeline {
  agent any

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }
    stage('Scan') {
      steps {
        script {
          def customImage = docker.build("mail-server-security-scanner:latest")
          sh 'echo "robalexdev.com" > list'
          sh 'mkdir -p results'
          customImage.inside {
            sh 'python manage.py makemigrations db'
            sh 'python manage.py migrate'
            sh 'python analyze.py list'
            sh 'python analyze.py'
          }
        }
      }
    }
  }

  post {
    always {
      cleanWs()
    }
  }
}
