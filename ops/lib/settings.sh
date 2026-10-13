# Reads non-secret settings from .env in the current directory. Source it.
# Units get .env through EnvironmentFile=; scripts run by hand use this.

# setting KEY
# Prints the value of the last KEY=value line in .env.
setting() {
	sed -n "s/^$1=//p" .env | tail -n 1
}
