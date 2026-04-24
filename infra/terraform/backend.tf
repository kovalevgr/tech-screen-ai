terraform {
  backend "gcs" {
    bucket = "tech-screen-493720-tf-state"
    prefix = "terraform/state"
  }
}
