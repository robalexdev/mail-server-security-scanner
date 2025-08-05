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
          sh 'mkdir -p results'

          copyArtifacts projectName: 'Measurements/tranco-list-cacher',
                        target: "tranco-list-cacher"

          // Extract just the top N domains
          sh 'cat tranco-list-cacher/output/tranco.csv | awk -F"," \'{ print $2 }\' | head -n 100 > list.txt'

          sh 'jenkins.sh'
          archiveArtifacts artifacts: 'results/results.db'
        }
      }
    }
  }

  post {
    always {
      steps {
        script {
          sh 'docker container rm app | true'
        }
        cleanWs()
      }
    }
  }
}
