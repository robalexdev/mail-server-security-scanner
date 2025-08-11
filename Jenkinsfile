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
          sh 'cat tranco-list-cacher/output/tranco.csv | awk -F"," \'{ print $2 }\' | head -n 100000 > list.txt'

          def pdnsImage = docker.image("powerdns/pdns-recursor-52:latest")
          def appImage = docker.build("app:latest")
          pdnsImage.withRun(
              " -p 1053:53" +
              " -p 1053:53/udp"
            ) { c ->
              appImage.inside(
                  " -v ${env.WORKSPACE}/results/:/app/results/" +
                  " -v ${env.WORKSPACE}/list.txt:/app/list.txt:ro" +
                  " --env MSSS_RESOLVERS=172.17.0.1" +
                  " --env MSSS_RESOLVER_PORT=1053"
                ) {
                  sh './run.sh'
              }
          }

          // Save database for additional analysis
          archiveArtifacts artifacts: 'results/results.db'
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
