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

          copyArtifacts projectName: 'Measurements/tranco-list-cacher',
                        target: "tranco-list-cacher"

          // Extract just the top N domains
          sh 'cat tranco-list-cacher/output/tranco.csv | awk -F"," \'{ print $2 }\' | head -n 10 > list.txt'

          customImage.inside {
            sh 'python manage.py makemigrations db'
            sh 'python manage.py migrate'
            sh 'python analyze.py list.txt'
            sh 'python analyze.py'
          }
          sh 'ls -Rl'
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
